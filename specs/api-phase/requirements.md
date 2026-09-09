# API Layer — Requirements

> EARS-style, derived from `specs/api-phase/design.md`. Each requirement is
> individually testable and traceable to a design.md section. IDs are
> referenced directly from `tasks.md` acceptance criteria — don't renumber
> without updating both.

## Notation

Four EARS patterns are used throughout:

- **Ubiquitous** — `THE SYSTEM SHALL <response>` — always true, no trigger.
- **Event-driven** — `WHEN <trigger> THE SYSTEM SHALL <response>` — fires on
  a specific request.
- **Unwanted behavior** — `IF <condition> THEN THE SYSTEM SHALL <response>`
  — an error/edge path.
- **State-driven** — `WHILE <state> THE SYSTEM SHALL <response>` — holds
  for the duration of a condition (mostly role/ownership gates here).

Every requirement carries an ID (`XC-1`, `AUTH-3`, etc.) referencing
`design.md §<n>`.

---

## 0. Cross-cutting (design.md §1)

**XC-1** (Ubiquitous) THE SYSTEM SHALL prefix every route with `/api/v1`.

**XC-2** (Ubiquitous) THE SYSTEM SHALL return timestamps as ISO 8601 UTC
with explicit offset (e.g. `2026-09-04T09:12:00Z`) in every response body.

**XC-3** (Ubiquitous) THE SYSTEM SHALL use UUID strings for every resource
`id` field, with no sequential or human-facing identifier.

**XC-4** (Event-driven) WHEN a request fails Pydantic validation THE SYSTEM
SHALL respond `422` with body `{ "error": { "code": "VALIDATION_ERROR",
"message": <string>, "fields": { <field_name>: [<message>, ...] } } }`,
mapping every failing field into `fields` — never FastAPI's default
`{"detail": [...]}` shape.

**XC-5** (Unwanted behavior) IF a request has no valid access-token cookie
on a protected route THEN THE SYSTEM SHALL respond `401` with `error.code =
"UNAUTHENTICATED"`.

**XC-6** (Unwanted behavior) IF an authenticated request's role does not
meet the route's minimum required role THEN THE SYSTEM SHALL respond `403`
with `error.code = "FORBIDDEN"`.

**XC-7** (Unwanted behavior) IF a requested resource does not exist, or
exists but the authenticated user lacks visibility into it THEN THE SYSTEM
SHALL respond `404` with `error.code = "NOT_FOUND"` — identical response
for both cases, so existence is never leaked to a caller without access.

**XC-8** (Ubiquitous) THE SYSTEM SHALL reject any client-supplied value for
a server-controlled field (`role` at registration, `requestor_id` /
`current_status_id` / `request_type` at request creation, `author_id` on
comments, `changed_by_id` on status changes) by ignoring it and deriving
the value server-side — never accept-and-override silently in a way that
differs from documented behavior; if a field is documented as "not
accepted," its presence in the body must not change the outcome.

**XC-9** (Ubiquitous) THE SYSTEM SHALL require a custom header
(`X-Requested-With: XMLHttpRequest`) on every non-`GET` request, and IF the
header is absent THEN THE SYSTEM SHALL respond `403` with `error.code =
"FORBIDDEN"` before evaluating any other request content (CSRF mitigation,
design.md §1).

**XC-10** (Ubiquitous) THE SYSTEM SHALL paginate every list endpoint with
`?page` (default `1`) and `?page_size` (default `20`, max `100`) query
params, returning `{ "items": [...], "total": <int>, "page": <int>,
"page_size": <int> }`.

**XC-11** (Unwanted behavior) IF `page_size` exceeds `100` THEN THE SYSTEM
SHALL clamp it to `100` rather than reject the request.

---

## 1. Auth (design.md §2)

### `POST /auth/register`

**AUTH-1** (Event-driven) WHEN a register request has valid `first_name`
(1–100 chars), `last_name` (1–100 chars), `email` (valid format), and
`password` (min 12 chars), and `email` is not already registered, THE
SYSTEM SHALL create a `users` row with `role = 'user'`, respond `201` with
the created user's `id`, `first_name`, `last_name`, `email`, `role`,
`created_at`, and SHALL NOT create a session (no cookies set).

**AUTH-2** (Unwanted behavior) IF `email` is already registered THEN THE
SYSTEM SHALL respond `409` with `error.code = "CONFLICT"` and SHALL NOT
reveal which specific field caused the conflict beyond the field name
`email` in the error (no user data leaked beyond "this email is taken").

**AUTH-3** (Unwanted behavior) IF `password` is fewer than 12 characters
THEN THE SYSTEM SHALL respond `422` per XC-4. **Length only — no
composition rule** (no required uppercase/digit/symbol). Decided
deliberately, not a placeholder: composition rules push toward predictable
substitutions (`P@ssw0rd1` satisfies most such rules and is a weak
password) without reliably improving actual strength; length is the
dominant factor, per NIST SP 800-63B's current guidance. Raised from an
earlier 8-char minimum for the same reason — length is where the real
protection comes from, so it's the lever that moved.

**AUTH-16** (Unwanted behavior) IF `password` exceeds `MAX_PASSWORD_BYTES`
(72 bytes — bcrypt's hard limit, exported as a named constant from
`app/core/security.py`, never a re-hardcoded literal in the schema) THEN
THE SYSTEM SHALL respond `422` per XC-4 with `fields.password` populated —
never a `500`. Note this is measured in **bytes, not characters**: a
password well under 72 characters can still exceed 72 bytes if it contains
multi-byte characters (emoji, non-Latin scripts). Found as a spec gap
during `T-AUTH-1` — `design.md §2` originally specified only a minimum.

**AUTH-4** (Ubiquitous) THE SYSTEM SHALL NOT accept a `role` field on
register, per XC-8.

**AUTH-5** (Ubiquitous) THE SYSTEM SHALL NOT include `password` or
`password_hash` in any response body, ever, under any endpoint.

### `POST /auth/login`

**AUTH-6** (Event-driven) WHEN a login request's `email` and `password`
match an existing, active user, THE SYSTEM SHALL set the access-token
cookie (1 hour expiry) and refresh-token cookie (30 day expiry), both
`httpOnly`, `Secure`, `SameSite=Lax`, and respond `200` with `id`,
`first_name`, `last_name`, `role`.

**AUTH-7** (Unwanted behavior) IF `email` does not match any user, OR
matches a user but `password` is incorrect, THEN THE SYSTEM SHALL respond
`401` with `error.code = "UNAUTHENTICATED"` and message `"Incorrect email
or password."` in both cases — identical response, no timing or content
difference that would let a caller distinguish "no such email" from "wrong
password."

**AUTH-8** (Unwanted behavior) IF the matched user's `is_active` is
`false` THEN THE SYSTEM SHALL respond `401` identically to AUTH-7 (no
distinct "account disabled" message — same non-enumeration reasoning).

### `POST /auth/refresh`

**AUTH-9** (Event-driven) WHEN a request carries a valid, unexpired,
unrevoked refresh-token cookie, THE SYSTEM SHALL mark the corresponding
`refresh_tokens` row `revoked_at = now()`, insert a new `refresh_tokens`
row, issue a new access-token cookie and new refresh-token cookie with the
same lifetimes as AUTH-6, and respond `200` with the same body shape as
login.

**AUTH-10** (Unwanted behavior) IF the refresh-token cookie is missing,
expired, or its `refresh_tokens` row has `revoked_at IS NOT NULL` THEN THE
SYSTEM SHALL respond `401` with `error.code = "UNAUTHENTICATED"` and SHALL
NOT issue new cookies.

**AUTH-11** (Unwanted behavior) IF an already-revoked refresh token is
presented (reuse of a rotated-out token) THEN THE SYSTEM SHALL, in
addition to AUTH-10's response, revoke every other non-revoked
`refresh_tokens` row for that `user_id` (token-family revocation on
suspected theft).

### `POST /auth/logout`

**AUTH-12** (Event-driven) WHEN an authenticated request hits this
endpoint, THE SYSTEM SHALL set `revoked_at = now()` on the current
refresh-token's `refresh_tokens` row, clear both cookies (expire
immediately), and respond `204` with an empty body.

**AUTH-13** (Unwanted behavior) IF no valid session exists THEN THE SYSTEM
SHALL still respond `204` (logout is idempotent — logging out twice is not
an error).

### `GET /auth/me`

**AUTH-14** (Event-driven) WHEN a request carries a valid access-token
cookie, THE SYSTEM SHALL respond `200` with `id`, `first_name`,
`last_name`, `role` for the authenticated user.

**AUTH-15** (Unwanted behavior) IF no valid access-token cookie is present
THEN THE SYSTEM SHALL respond `401` per XC-5 — SHALL NOT attempt to fall
back to the refresh-token cookie (that's what `/auth/refresh` is for; `/me`
does not silently refresh).

---

## 2. Statuses (design.md §3)

**ST-1** (Ubiquitous) THE SYSTEM SHALL respond `200` to `GET /statuses`
with no authentication required.

**ST-2** (Ubiquitous) THE SYSTEM SHALL return all four seeded `statuses`
rows (`open`, `in_progress`, `resolved`, `closed`) ordered ascending by
`sort_order`, as a bare `{ "items": [...] }` array (not the paginated
envelope — there are always exactly four rows).

---

## 3. Service Requests (design.md §4)

### `GET /service-requests`

**SR-1** (State-driven) WHILE the authenticated user's role is `user`, THE
SYSTEM SHALL scope results to `requestor_id = <authenticated user id>`
only.

**SR-2** (State-driven) WHILE the authenticated user's role is `admin`, THE
SYSTEM SHALL return results across all requestors.

**SR-3** (Event-driven) WHEN `?status=<name>` is supplied, THE SYSTEM
SHALL filter to requests whose current status name matches; IF `<name>`
does not match any seeded status THEN THE SYSTEM SHALL respond `422` per
XC-4 rather than silently returning an empty list.

**SR-4** (Event-driven) WHEN `?priority=<value>` is supplied with
`value ∈ {low, medium, high}`, THE SYSTEM SHALL filter accordingly; IF
`value` is outside that set THEN THE SYSTEM SHALL respond `422`.

**SR-5** (Ubiquitous) THE SYSTEM SHALL return the full `ServiceRequest`
shape (including `description`) for every item in the list response — not
a reduced summary shape (design.md §0 decision 2).

### `POST /service-requests`

**SR-6** (Event-driven) WHEN a create request has valid `title` (1–200
chars), `description` (1–10000 chars), and `priority ∈ {low, medium,
high}`, THE SYSTEM SHALL create a `service_requests` row with
`requestor_id` = the authenticated user's id, `request_type = 'general'`,
`current_status_id` = the `'open'` status's id, and respond `201` with the
full created `ServiceRequest`.

**SR-7** (Unwanted behavior) IF `title` is missing or empty, or exceeds
200 chars, THEN THE SYSTEM SHALL respond `422` with `fields.title`
populated.

**SR-8** (Unwanted behavior) IF `description` is missing, empty, or
exceeds 10000 chars, THEN THE SYSTEM SHALL respond `422` with
`fields.description` populated.

**SR-9** (Unwanted behavior) IF `priority` is missing or not one of `low
/ medium / high` THEN THE SYSTEM SHALL respond `422` with
`fields.priority` populated.

**SR-10** (Ubiquitous) THE SYSTEM SHALL ignore any client-supplied
`request_type`, `requestor_id`, or `current_status_id` field in the
request body, per XC-8.

### `GET /service-requests/{id}`

**SR-11** (Event-driven) WHEN the authenticated user is the request's
`requestor_id`, OR the authenticated user's role is `admin`, THE SYSTEM
SHALL respond `200` with the full `ServiceRequest`.

**SR-12** (Unwanted behavior) IF the authenticated user is neither the
requestor nor an admin THEN THE SYSTEM SHALL respond `404` per XC-7 (not
`403` — existence isn't confirmed to a caller without access).

**SR-13** (Unwanted behavior) IF `{id}` is not a valid UUID, or matches no
row, THEN THE SYSTEM SHALL respond `404`.

---

## 4. Status changes (design.md §5)

### `GET /service-requests/{id}/status-changes`

**SC-1** (Event-driven) WHEN the caller has visibility into the parent
request (SR-11's rule), THE SYSTEM SHALL respond `200` with a paginated
list of `StatusChange` ordered `changed_at` ascending.

**SC-2** (Unwanted behavior) IF the caller lacks visibility into the
parent request THEN THE SYSTEM SHALL respond `404`, matching SR-12.

**SC-3** (Ubiquitous) THE SYSTEM SHALL return only rows that actually
exist in `status_history` — SHALL NOT synthesize placeholder rows for
statuses not yet reached (design.md §0 decision, locked project decision).

### `POST /service-requests/{id}/status-changes`

**SC-4** (State-driven) WHILE the authenticated user's role is `admin`, THE
SYSTEM SHALL accept this request; WHILE role is `user`, THE SYSTEM SHALL
reject it per XC-6 (`403`).

**SC-5** (Event-driven) WHEN `status_id` references an existing `statuses`
row, THE SYSTEM SHALL, in a single transaction: insert a `status_history`
row (`status_id`, `changed_by_id` = authenticated admin's id, `note` if
supplied, `changed_at = now()`) AND update the parent
`service_requests.current_status_id` to match, then respond `201` with the
created `StatusChange`.

**SC-6** (Unwanted behavior) IF `status_id` is missing or does not match
any `statuses` row THEN THE SYSTEM SHALL respond `422` with
`fields.status_id` populated, and SHALL NOT partially apply the change
(no orphaned history row without a matching `current_status_id` update, or
vice versa).

**SC-7** (Ubiquitous) THE SYSTEM SHALL accept an optional `note` (no
enforced max beyond the `TEXT` column's practical limits) and store it
verbatim, `null` if omitted.

**SC-8** (Unwanted behavior) IF the target `{id}` service request does not
exist, or the caller lacks visibility into it, THEN THE SYSTEM SHALL
respond `404` before evaluating `status_id`.

---

## 5. Comments (design.md §6)

### `GET /service-requests/{id}/comments`

**CM-1** (Event-driven) WHEN the caller has visibility into the parent
request, THE SYSTEM SHALL respond `200` with a paginated list of `Comment`
ordered `created_at` ascending.

**CM-2** (State-driven) WHILE the authenticated user's role is `user`, THE
SYSTEM SHALL exclude every comment with `is_internal = true` from the
response — filtered at the query level, never included-then-hidden.

**CM-3** (State-driven) WHILE the authenticated user's role is `admin`, THE
SYSTEM SHALL include comments regardless of `is_internal`, with the field
visible on each.

**CM-4** (Unwanted behavior) IF the caller lacks visibility into the
parent request THEN THE SYSTEM SHALL respond `404`, matching SR-12.

### `POST /service-requests/{id}/comments`

**CM-5** (Event-driven) WHEN `body` is 1–5000 chars and the caller has
visibility into the parent request, THE SYSTEM SHALL create a `comments`
row with `author_id` = the authenticated user's id and respond `201` with
the created `Comment`.

**CM-6** (Unwanted behavior) IF `body` is missing, empty, or exceeds 5000
chars THEN THE SYSTEM SHALL respond `422` with `fields.body` populated.

**CM-7** (State-driven) WHILE the authenticated user's role is `user`, IF
the request body includes `"is_internal": true` THEN THE SYSTEM SHALL
respond `403` with `error.code = "FORBIDDEN"` and SHALL NOT create the
comment — the field is rejected outright, never silently coerced to
`false` (design.md §6, locked project decision 3).

**CM-8** (State-driven) WHILE the authenticated user's role is `admin`,
THE SYSTEM SHALL accept `is_internal` as either `true` or `false` (default
`false` if omitted).

**CM-9** (Unwanted behavior) IF the caller lacks visibility into the
parent request THEN THE SYSTEM SHALL respond `404` before evaluating
`body` or `is_internal`.

---

## 6. Traceability

Every requirement above maps to exactly one `design.md` section; `tasks.md`
acceptance criteria will reference these IDs directly (e.g. "verify AUTH-6
through AUTH-8"), so a task's Claude Code prompt can point at this file
instead of restating validation rules inline. If a design.md decision
changes, update the corresponding requirement ID here in the same edit —
don't let the two drift.
