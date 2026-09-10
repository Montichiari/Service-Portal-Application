# API Layer — Design

> Informed by `backend/specs/backend-phase/design.md` (locked schema) and
> `frontend-contract.md` (as-is frontend assumptions), the same way the
> backend `design.md` was informed by the ERD. This document is the source
> of truth until `openapi.yaml` is generated from it; where they disagree,
> this document wins and `openapi.yaml` needs updating.

## 0. Reconciliation decisions (this document, beyond the four already locked)

1. **Casing: snake_case everywhere** — request bodies, response bodies, query
   params. Resolves frontend-contract §3.3 / §9-#6 (mixed snake_case/camelCase
   in `MockRequestDetail`). Matches FastAPI/Pydantic defaults; no alias
   configuration needed.
2. **One `ServiceRequest` shape for list and detail**, not two. Both carry
   `created_at` and `updated_at` always. Detail adds `description`. Resolves
   §3.1 (list/detail shared no timestamp field).
3. **Comments and status history are sub-resource collections**, never
   embedded on the request payload. Resolves §6.2 and extends the
   already-locked status-changes sub-resource pattern to comments for the
   same reason: unbounded child collections don't belong inlined on a parent
   that's also paginated in a list.
4. **`author` / `changed_by` are structured user-summary objects**, never
   pre-formatted display strings. Resolves §6.3 (`'Priya Nair — IT Service
Desk'` fused string). Display formatting is a frontend concern.
5. **Registration collects `first_name` + `last_name`**, not a single
   `full_name`. Required because `users` has two NOT NULL columns and no
   reliable server-side split exists. **Frontend change required** in the
   Auth slice: `RegisterPage`/`registerSchema` lose `fullName`, gain two
   fields.
6. **Login authenticates on `email`**, not `username`. **Frontend change
   required**: `LoginPage`/`loginSchema` field renamed and given
   `type="email"` validation, matching the register form's identifier.
7. **`GET /auth/me` added** — not present in either source document. Needed
   because cookie-based server-side sessions replace the frontend's
   in-memory `role` state (frontend-contract §1.2), so the frontend needs an
   explicit way to bootstrap "who am I" on page load / after a hard
   navigation (§8.6 notes `AppShell` nav already forces reloads).
8. **Ticket-number display (`#4271`, frontend-contract §3.2) is resolved: no
   migration.** No `ticket_number` column is added. The API exposes only the
   UUID `id`; the frontend drops the short-number display convention and
   shows the full UUID in its place (e.g. request headings, list rows).
   Recommended alternative (a sequential `ticket_number` column, cheap to
   add pre-launch) was raised and explicitly declined — recorded here so
   it's not silently revisited later without noting the tradeoff was seen.
9. **Custom error envelope**, overriding FastAPI's default validation-error
   shape. One consistent shape for validation errors, auth errors, and
   not-found errors, rather than a different shape per error class.
10. **No write endpoints beyond what the current frontend scope needs.**
    No `PATCH /service-requests/{id}` for reassignment/priority-edit yet —
    nothing in the frontend prototype exercises it, and adding it
    speculatively means designing and testing a contract nobody's using.
    Noted as a deferred item, not built.

## 1. Cross-cutting conventions

### Base path

All endpoints are under `/api/v1`.

### Auth transport

- Access token: short-lived JWT, `httpOnly`, `Secure`, `SameSite=Lax` cookie
  (per locked decision — never in the response body).
- Refresh token: long-lived opaque token, same cookie attributes, separate
  cookie name. Its hash is stored in `refresh_tokens` (already in the
  schema) so it can be revoked — this is _why_ that table exists.
- No `Authorization: Bearer` header flow for the browser client. (If a
  future non-browser client needs the API, that's a separate auth strategy,
  not this one.)
- **CSRF**: cookie-based auth without a bearer header is CSRF-exposed by
  default. `SameSite=Lax` blocks cross-site POST from top-level navigation
  but not from same-site-adjacent vectors depending on browser behavior.
  **Decided**: state-changing endpoints (`POST`/`PUT`/`PATCH`/`DELETE`)
  require a custom header (`X-Requested-With` — presence only, any value;
  the protection is that a cross-site form post can't set custom headers
  at all, not what the header says, so pinning to an exact value like
  `XMLHttpRequest` adds nothing and only breaks clients that spell it
  differently) — a lightweight check, not a full double-submit-cookie
  scheme. `GET`, `HEAD`, and `OPTIONS` are exempt — `OPTIONS` specifically
  because it's the browser's own CORS preflight, sent automatically and
  incapable of carrying a custom header. Adequate for this project's
  scope; revisit before any real deployment beyond the capstone demo.
- **CORS**: `FRONTEND_ORIGIN` (an explicit configured origin) is allowed
  via CORS middleware with `allow_credentials=True` — never a wildcard
  origin, which the CORS spec itself makes incompatible with credentialed
  requests (browsers reject that combination). **This was missing from
  the original draft of this document** — found during `T-AUTH-2`'s
  review, before it could silently break `T-AUTH-4`'s browser-based fetch
  calls. Without it, every cookie-bearing cross-origin request from the
  frontend dev server is blocked by the browser before any backend code
  even runs.
- **Rate limiting** on `/auth/login`: **deferred**, not built in this
  phase. No brute-force protection exists yet — noted explicitly rather
  than silently absent, and picked back up in a later hardening pass (see
  §7).

### JWT claims

```json
{
  "sub": "<user.id UUID>",
  "role": "user | admin",
  "iat": 1234567890,
  "exp": 1234567890,
  "jti": "<token id, for logging/revocation correlation>"
}
```

`role` is embedded in the claims, but **the backend does not trust that
claim value directly** — `get_current_user` re-loads the user's row from
the database on every protected request (`XC-13`), so `role` (and every
other field it returns) reflects current state, not what was true when the
token was issued. **Decided during `T-AUTH-2`**, reversing this section's
original draft rationale (which assumed a claims-only check specifically
to avoid a DB hit per request): the tradeoff — one extra query per
protected request — buys immediate effect for deactivation or deletion,
rather than a stale token remaining valid for up to its full 1-hour
lifetime after either happens. Worth naming plainly since it contradicts
the naive read of "why put `role` in a JWT at all if you're going to hit
the DB anyway": the claim is still useful as a _cheap pre-check_ before
the query (an obviously-tampered or expired token is rejected without
touching the database at all) — it's just not the final word on role.

**Lifetimes**: access token `exp` = 1 hour from issue. Refresh token
(opaque, stored hashed in `refresh_tokens`) = 30 days from issue,
single-use — rotated on every `/auth/refresh` call (old row marked
`revoked_at`, new row inserted). A 30-day refresh window means a signed-in
user stays signed in across normal usage gaps without re-entering
credentials; the 1-hour access token limits how long a stolen access token
(e.g. via XSS) stays useful before it must be refreshed again.

### Pagination

List endpoints return an envelope, not a bare array — resolves
frontend-contract §8.1 ("no response envelope is assumed" — that was true of
the _prototype_, not a constraint we need to carry forward):

```json
{
  "items": [
    /* resource objects */
  ],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

Query params: `?page=1&page_size=20` (defaults `page=1`, `page_size=20`, max
`page_size=100`). Offset/limit-style paging, not cursor-based — the data
volumes here don't justify cursor pagination's complexity, and offset
paging is simpler to reason about while learning.

### Timestamps

ISO 8601, UTC, with offset (`2026-09-04T09:12:00Z`). Resolves frontend
contract §3.4 (three inconsistent pre-formatted date strings) — the API
emits one machine-readable format always; relative ("2h ago") or localized
display formatting is entirely a frontend concern, done at render time, not
baked into the payload.

### IDs

UUID strings everywhere (matches the locked schema's UUID PKs). No
`ticket_number` column, no sequential human-facing number — decided in §0.
The frontend displays the full UUID wherever the prototype showed a short
`#4271`-style number (list rows, request detail heading, links). This is a
visible UX regression from what the prototype _implied_ (not what it
actually typed — §3.2 notes the prototype's `id` was only ever `string`);
worth a conscious look once the UI is live, but not blocking this contract.

### Standard object shapes referenced throughout

**`UserSummary`** (embedded wherever a user reference appears — comment
authors, status-change actors, request assignees):

```json
{
  "id": "uuid",
  "first_name": "Priya",
  "last_name": "Nair",
  "role": "admin"
}
```

Deliberately _not_ the full `User` resource (no email, no timestamps) — this
is a reference for display, not an identity endpoint.

**`Status`**:

```json
{
  "id": "uuid",
  "name": "in_progress",
  "sort_order": 2,
  "is_terminal": false
}
```

### Error envelope

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "One or more fields are invalid.",
    "fields": {
      "email": ["Enter a valid email address"],
      "password": ["Password must be at least 8 characters"]
    }
  }
}
```

`fields` is present only for `VALIDATION_ERROR` (422); other error codes omit
it. This means FastAPI's default `RequestValidationError` handler gets
overridden to reshape Pydantic's error list into this `fields` map — a
deliberate contract decision, not FastAPI's default behavior.

| HTTP | `code`             | When                                                                                     |
| ---- | ------------------ | ---------------------------------------------------------------------------------------- |
| 400  | `BAD_REQUEST`      | Malformed request the schema can't even parse                                            |
| 401  | `UNAUTHENTICATED`  | Missing/expired/invalid access token                                                     |
| 403  | `FORBIDDEN`        | Valid session, insufficient role (e.g. non-admin posting an internal comment)            |
| 404  | `NOT_FOUND`        | Resource doesn't exist, or exists but the user can't see it                              |
| 409  | `CONFLICT`         | e.g. register with an email already in use                                               |
| 422  | `VALIDATION_ERROR` | Field-level validation failure                                                           |
| 500  | `INTERNAL_ERROR`   | Unhandled — body still follows the envelope, `message` is generic, never leaks internals |

### Role enforcement

Checked once, centrally (a FastAPI dependency), not re-implemented per
route. Every protected route declares the minimum role it needs; the
dependency reads `role` off the validated JWT claim, never off the request
body — consistent with the locked decision that role is never accepted from
the client.

---

## 2. Auth

### `POST /auth/register`

No auth required.

Request:

```json
{
  "first_name": "Daniel",
  "last_name": "Osei",
  "email": "daniel.osei@example.com",
  "password": "at-least-12-characters-long"
}
```

- `first_name`, `last_name`: 1–100 chars (matches `users` column limits)
- `email`: valid email, unique — 409 `CONFLICT` if already registered
- `password`: min 12 chars, **max 72 bytes** (`AUTH-16`) — the max is
  bcrypt's hard limit, found during `T-AUTH-1`; the min is a deliberate
  length-only policy (`AUTH-3`), not a placeholder — no composition rule
  (no required uppercase/digit/symbol). Composition rules are weaker than
  they look (they push toward predictable substitutions attackers already
  model for) and length is the dominant factor in actual strength, per
  current NIST guidance — so length is the one lever this policy pulls.
  The max is enforced against the exported `MAX_PASSWORD_BYTES` constant
  from `app/core/security.py`, never a second hardcoded `72` in the schema
  — one number, one source. Bytes, not characters: a password well under
  72 characters can still exceed 72 bytes with multi-byte characters.
  **Not** echoed or returned in any response, ever.
- No `role` field accepted — every new user is created with the DB default
  (`'user'`). Promotion to admin is an out-of-band operation (direct DB
  action or a future admin-only endpoint), never self-service.

Response `201`:

```json
{
  "id": "uuid",
  "first_name": "Daniel",
  "last_name": "Osei",
  "email": "daniel.osei@example.com",
  "role": "user",
  "created_at": "2026-09-04T09:12:00Z"
}
```

Does **not** log the user in — register then redirect to login, matching
the frontend prototype's existing flow (§2.3), just now with a real record
created instead of the fields being discarded.

### `POST /auth/login`

No auth required.

Request:

```json
{ "email": "daniel.osei@example.com", "password": "at-least-8-chars" }
```

On success: sets the access-token and refresh-token cookies, returns `200`:

```json
{ "id": "uuid", "first_name": "Daniel", "last_name": "Osei", "role": "user" }
```

On failure (wrong email or password — **do not distinguish which** in the
response, that's a user-enumeration leak): `401 UNAUTHENTICATED`,
`message: "Incorrect email or password."` — deliberately mirrors the
prototype's existing non-committal copy (§2.2), now backed by a real check
instead of a `===` against two constants.

### `POST /auth/refresh`

**Built now, fully wired** — not deferred to backend Phase 3.

Requires a valid refresh-token cookie (not the access token — the access
token may already be expired, that's the point of this endpoint).

Rotates the refresh token: the old one is marked `revoked_at` in
`refresh_tokens`, a new one is issued and stored. Single-use rotation, not a
long-lived reusable refresh token — if a refresh token is ever replayed
after rotation, that's a signal of theft, and the whole family can be
revoked (implementation detail for the backend slice, contract-relevant
because it's _why_ `revoked_at` exists on the table).

Response `200`: same body shape as login. Sets new cookies.

### `POST /auth/logout`

Requires an authenticated session.

Revokes the current refresh token (`revoked_at` set), clears both cookies.
Response `204`, empty body.

### `GET /auth/me`

Requires an authenticated session.

Response `200`: same shape as login's success body. `401` if no valid
session — this is the frontend's session-bootstrap call, made once on app
load to determine signed-in state instead of trusting in-memory state that
a page reload would have wiped anyway.

---

## 3. Statuses

### `GET /statuses`

No auth required (used to populate the status-stepper UI, which non-admins
also view).

Response `200`:

```json
{
  "items": [
    { "id": "uuid", "name": "open", "sort_order": 1, "is_terminal": false },
    {
      "id": "uuid",
      "name": "in_progress",
      "sort_order": 2,
      "is_terminal": false
    },
    { "id": "uuid", "name": "resolved", "sort_order": 3, "is_terminal": true },
    { "id": "uuid", "name": "closed", "sort_order": 4, "is_terminal": true }
  ]
}
```

Ordered by `sort_order` — per the already-locked reconciliation decision #1.
Not paginated (there are exactly four rows, always; wrapping this in the
generic list envelope would be ceremony with no payoff). The frontend
merges this against real status-change history client-side to render
filled/hollow steps — per locked decision #2, this endpoint plus
`GET .../status-changes` together _are_ that merge's two inputs.

---

## 4. Service Requests

### `ServiceRequest` shape (list and detail — decision #2 above)

```json
{
  "id": "uuid",
  "title": "VPN not connecting",
  "request_type": "general",
  "priority": "high",
  "status": {
    "id": "uuid",
    "name": "in_progress",
    "sort_order": 2,
    "is_terminal": false
  },
  "requestor": {
    "id": "uuid",
    "first_name": "Daniel",
    "last_name": "Osei",
    "role": "user"
  },
  "assignee": null,
  "created_at": "2026-09-04T09:12:00Z",
  "updated_at": "2026-09-08T06:30:00Z",
  "description": "..."
}
```

`description` is included in both list and detail responses in this
version of the contract — the payload cost of one text field on a
paginated list is low, and having two divergent shapes is exactly the
inconsistency being resolved. If list payload size becomes a real problem
later, splitting it out is a documented, deliberate follow-up, not a
silent default.

### `GET /service-requests`

Requires auth. Regular users see only their own requests
(`requestor_id = current_user`); admins see all. This is enforced in the
query, not filtered client-side after fetch.

Query params: `?page=1&page_size=20&status=in_progress&priority=high`
(`status`/`priority` filters optional).

Response `200`: paginated envelope of `ServiceRequest`.

### `POST /service-requests`

Requires auth (any authenticated role).

Request:

```json
{ "title": "VPN not connecting", "description": "...", "priority": "high" }
```

- `title`: 1–200 chars (matches column)
- `description`: 1–10000 chars — frontend-contract §8.7 caps the prototype
  form at 1000 chars client-side; the DB column is unbounded `TEXT`, so the
  API's real ceiling is a deliberate, generous validation limit, not the
  column type. Worth a decision: **keep the frontend's 1000-char UX limit**,
  set the API validation ceiling higher (10000) as a backstop against abuse
  rather than the actual intended limit.
- `priority`: `low | medium | high`, required (matches frontend's required
  field, §5)
- `request_type`: **not accepted** — server always sets `'general'`,
  matching the locked schema decision that this is a disabled placeholder
  field, not a real client choice yet (frontend-contract §3.6, and the
  submit schema already deliberately excludes it, §8.7)
- `requestor_id`: **not accepted** — always the authenticated user's ID,
  never client-supplied
- `current_status_id`: **not accepted** — server sets it to `'open'`'s ID on
  insert (per the locked DB decision that there's no DB-level default)

Response `201`: the created `ServiceRequest`.

### `GET /service-requests/{id}`

Requires auth. `404 NOT_FOUND` (not `403`) if the request exists but
belongs to another non-admin user — existence shouldn't be leakable to
someone who can't see the resource. Admins can fetch any request.

Response `200`: `ServiceRequest`.

---

## 5. Status changes (sub-resource)

Already locked: status transitions are `POST
/service-requests/{id}/status-changes`, never a direct field mutation —
this section fills in the shape and adds the matching `GET`.

### `StatusChange` shape

```json
{
  "id": "uuid",
  "status": {
    "id": "uuid",
    "name": "in_progress",
    "sort_order": 2,
    "is_terminal": false
  },
  "changed_by": {
    "id": "uuid",
    "first_name": "Priya",
    "last_name": "Nair",
    "role": "admin"
  },
  "note": "Escalated to network team.",
  "changed_at": "2026-09-08T06:30:00Z"
}
```

`changed_by` is nullable (matches the DB's `SET NULL` on delete — a status
change from a since-deleted user still has a record, just an anonymous one).

### `GET /service-requests/{id}/status-changes`

Requires auth, same visibility rule as the parent request (owner or admin).

Response `200`: paginated envelope of `StatusChange`, ordered `changed_at`
ascending. **Only real transitions, real timestamps** — no synthetic
placeholder rows for un-reached future steps (locked decision #2). Resolves
frontend-contract §7.2's most consequential assumption: the prototype's
fixed five-row template with `timestamp: null` placeholders doesn't exist
in the real contract at all. The frontend reconstructs the
filled/hollow-step visual by merging this array against `GET /statuses` —
any status in the lookup table with no matching entry here is unreached,
rendered hollow. That merge logic lives entirely in the frontend; the API
just tells the truth about what happened.

### `POST /service-requests/{id}/status-changes`

Requires **admin** role — regular users don't transition their own
requests' status (nothing in the frontend prototype suggests otherwise;
"Assigned to IT Service Desk", frontend-contract §7.4, implies a service
desk / admin actor performs transitions).

Request:

```json
{ "status_id": "uuid", "note": "Escalated to network team." }
```

- `status_id`: required, must reference an existing row in `statuses`
- `note`: optional, matches the nullable `note` column

Server also updates `service_requests.current_status_id` to match, in the
same transaction that inserts the `status_history` row — these two writes
must not be allowed to diverge.

Response `201`: the created `StatusChange`.

---

## 6. Comments

### `Comment` shape

```json
{
  "id": "uuid",
  "author": {
    "id": "uuid",
    "first_name": "Priya",
    "last_name": "Nair",
    "role": "admin"
  },
  "body": "Please try restarting your VPN client.",
  "is_internal": false,
  "created_at": "2026-09-04T14:10:00Z",
  "updated_at": "2026-09-04T14:10:00Z"
}
```

Resolves frontend-contract §6.3 (fused `author` string) and §6.4 (no stable
key — `id` is now real, so list rendering can key on it instead of array
index).

### `GET /service-requests/{id}/comments`

Requires auth, same visibility rule as the parent request.

- **Regular users**: never receive comments where `is_internal = true` —
  filtered server-side, not just hidden in the UI. This is the same trust
  boundary principle as role enforcement generally: a client-side filter on
  data the server already sent would be a real information leak (a user
  who opens devtools' network tab would see internal notes about their own
  ticket).
- **Admins**: receive all comments, `is_internal` visible on each.

Response `200`: paginated envelope of `Comment`, ordered `created_at`
ascending.

### `POST /service-requests/{id}/comments`

Requires auth. Any authenticated user with visibility into the parent
request may comment on it (owner or admin) — resolves frontend-contract
§6.5 (no create path existed at all in the prototype; this is new surface,
not a reconciliation of an existing one).

Request:

```json
{ "body": "Any update on this?", "is_internal": false }
```

- `body`: 1–5000 chars
- `is_internal`: optional, defaults `false`. **Enforced per locked decision
  3**: if a non-admin includes `is_internal: true`, that's `403 FORBIDDEN`
  — rejected outright, not silently coerced to `false`. Silently
  downgrading it would let a regular user believe their comment was marked
  internal when it wasn't; an explicit rejection is honest about what
  happened.

Response `201`: the created `Comment`, `author` populated from the
authenticated session (never client-supplied).

---

## 7. Deferred / open decisions

- **`PATCH /service-requests/{id}`** for admin reassignment / priority
  edits: not built yet — no current frontend surface drives it. Add when a
  frontend page actually needs it, with its own requirements pass, rather
  than guessing the shape now.
- **`request_type` beyond `'general'`**: the schema/API both keep this
  locked to one value for now, per the existing disabled-placeholder
  decision. Whenever a second type is designed, it'll need both a
  migration-free path (the `request_metadata` JSONB column already exists
  for this) and a Pydantic discriminated-union validation model keyed on
  `request_type`, per the schema decision already on record.
- **Rate limiting / brute-force protection on `/auth/login`**: explicitly
  deferred to a later hardening pass (decided, not an oversight — see §1).
  Pick this back up before this goes anywhere near a public network, even
  for a capstone demo.
