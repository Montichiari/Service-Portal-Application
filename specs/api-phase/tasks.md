# API Layer — Tasks

> Ordered Claude Code prompts. One task per session, `/clear` between tasks,
> manual review + commit before starting the next — per `ways-of-working`.
> Every acceptance criterion cites a `requirements.md` ID; if you need to
> know _why_ a criterion exists, that ID is where the reasoning lives, not
> here.

## Conventions for this file

- **Task prompts state outcomes and requirement IDs, never current frontend
  code contents.** `frontend-contract.md` is a snapshot (as of commit
  `d027439`); the live repo may have moved since. Every frontend task below
  instructs Claude Code to read the current file first and reconcile it to
  the cited requirements — not to trust this document's description of
  what that file currently contains.
- **Frontend data-fetching approach, decided here (not in design.md,
  because it's an implementation detail, not a contract detail):** a small
  hand-written `src/lib/api.ts` client wrapping `fetch`
  (`credentials: 'include'` for cookies, the `X-Requested-With` header
  from `XC-9` on every non-GET call, a single silent
  refresh-and-retry on a `401`). No TanStack Query or similar dependency
  added. Rationale: the frontend currently has zero data-fetching
  dependencies by deliberate design
  (`frontend-contract.md §0`), and the four vertical slices here don't
  need caching, background refetch, or optimistic updates — a fetch
  wrapper is the minimum that satisfies the actual requirements. If a
  later slice needs real caching behavior, add the dependency then, with
  its own justification, rather than defaulting to it now.
- No new Alembic migration is needed anywhere in this phase — the
  ticket-number column was explicitly declined (`design.md §0`), and every
  other model needed already exists from the ORM phase.

---

## Group 1 — Auth

### T-AUTH-0 — Verify current frontend auth state (read-only)

**Goal**: Confirm what `LoginPage.tsx`, `RegisterPage.tsx`,
`loginSchema.ts`, `registerSchema.ts`, and `AuthContext.tsx` actually
contain right now, before any of it gets rewritten.

**Scope**: No code changes. Read the five files above as they exist in the
repo today. Report:

- Anything that no longer matches `frontend-contract.md`'s description
  (§1, §2) — field names, validation rules, the demo-credential constants,
  the two-sign-in-paths behavior.
- Any file among the five that no longer exists, or that's moved.
- Anything relevant that `frontend-contract.md` didn't cover.

(Already confirmed, no need to re-check: `routes.tsx` does not exist —
routing is inline and unguarded in `App.tsx`. See `frontend/CLAUDE.md`'s
Auth guard pattern section.)

**Acceptance criteria**:

- [ ] A short written diff-from-contract report, not a rewrite of the
      contract document itself
- [ ] No files modified

**Stop here.** Review the report before starting T-AUTH-1 — if drift is
significant, the later Auth tasks in this group may need their acceptance
criteria adjusted first.

---

### T-AUTH-1 — Backend auth utilities

**Goal**: Password hashing and JWT helpers, with no endpoints wired yet —
this is the foundation the next two tasks build on.

**Covers**: supports `AUTH-1` through `AUTH-15` indirectly (no requirement
IDs are independently testable at this layer — that's expected, this is
infrastructure).

**Scope**:

- Password hashing (`passlib[bcrypt]` or equivalent) — hash on register,
  verify on login. Never store or log a plaintext password.
- JWT encode/decode helpers matching the claims shape in `design.md §1`
  (`sub`, `role`, `iat`, `exp`, `jti`).
- Cookie-setting helpers for access token (1 hr) and refresh token
  (30 day), `httpOnly` / `Secure` / `SameSite=Lax`, per `design.md §1` and
  `AUTH-6`.
- Refresh-token hashing (store the hash in `refresh_tokens.token_hash`,
  never the raw token) and a lookup/verify helper.

**Acceptance criteria**:

- [ ] Unit tests: a hashed password verifies correctly and a wrong
      password fails verification
- [ ] Unit tests: a JWT round-trips (encode then decode yields the same
      claims) and an expired/tampered token fails decode
- [ ] No endpoint routes added in this task

---

### T-AUTH-2 — Cross-cutting error envelope, auth dependency, CSRF check

**Goal**: The three pieces of middleware every protected route in every
future slice depends on — build them once, here, correctly.

**Covers**: `XC-4`, `XC-5`, `XC-6`, `XC-9`.

**Scope**:

- Override FastAPI's default `RequestValidationError` handler to emit the
  `{ "error": { "code": "VALIDATION_ERROR", ... "fields": {...} } }` shape
  from `XC-4`. Add a generic exception handler for uncaught errors →
  `500` / `INTERNAL_ERROR`, message never leaks internals.
- An auth dependency (`get_current_user`) that reads the access-token
  cookie, decodes it, loads (or just trusts the claims for) the user —
  raises the `401`/`UNAUTHENTICATED` shape on missing/invalid/expired
  token (`XC-5`).
- A role-check dependency (`require_role("admin")` or similar) that raises
  `403`/`FORBIDDEN` when the authenticated user's role doesn't match
  (`XC-6`).
- Middleware or dependency enforcing `X-Requested-With` on every non-`GET`
  request (`XC-9`), `403`/`FORBIDDEN` if absent.

**Acceptance criteria**:

- [ ] `XC-4`: a request with an invalid field returns the custom envelope,
      not FastAPI's default shape
- [ ] `XC-5`: a protected route with no cookie returns `401` in the
      correct envelope
- [ ] `XC-6`: a `require_role("admin")` route hit by a `user`-role token
      returns `403`
- [ ] `XC-9`: a `POST` with no `X-Requested-With` header returns `403`
      before any route logic runs
- [ ] No auth _endpoints_ added yet — this is middleware only, exercised
      via a minimal throwaway test route if there's nothing real to hang
      it on yet

---

### T-AUTH-3 — Auth endpoints

**Goal**: The five real endpoints, built on T-AUTH-1 and T-AUTH-2.

**Covers**: `AUTH-1` through `AUTH-15`.

**Scope**: Implement in this order (each depends on the last):

1. `POST /auth/register` — `AUTH-1` through `AUTH-5`
2. `POST /auth/login` — `AUTH-6` through `AUTH-8`
3. `GET /auth/me` — `AUTH-14`, `AUTH-15` (simplest protected route, good
   smoke test for T-AUTH-2's dependency)
4. `POST /auth/refresh` — `AUTH-9` through `AUTH-11`
5. `POST /auth/logout` — `AUTH-12`, `AUTH-13`

**Acceptance criteria** (contract tests, real Postgres, per
`backend/CLAUDE.md`'s testing convention):

- [ ] `AUTH-1`: valid register creates a `user`-role row, returns `201`,
      no cookies set
- [ ] `AUTH-2`: duplicate email returns `409`
- [ ] `AUTH-4`: a `role` field in the register body is ignored, not
      applied
- [ ] `AUTH-5`: no response body anywhere contains `password` or
      `password_hash`
- [ ] `AUTH-6`: valid login sets both cookies with correct attributes and
      expiries
- [ ] `AUTH-7`: wrong email and wrong password produce byte-identical
      error bodies
- [ ] `AUTH-9`: refresh rotates the token (old row `revoked_at` set, new
      row inserted) and issues new cookies
- [ ] `AUTH-11`: replaying an already-rotated refresh token revokes the
      rest of that user's active refresh tokens
- [ ] `AUTH-12`/`AUTH-13`: logout is idempotent, always `204`

---

### T-AUTH-4 — Frontend API client

**Goal**: The `src/lib/api.ts` fetch wrapper described in this file's
conventions section — no page changes yet.

**Scope**:

- `credentials: 'include'` on every call
- `X-Requested-With` header on every non-`GET` call
- On a `401` from any call other than `/auth/refresh` itself, attempt one
  silent `POST /auth/refresh`, then retry the original call once; if the
  refresh also fails, surface the original `401` to the caller
- A typed error shape matching the `error.code` / `error.message` /
  `error.fields` envelope, so calling code can branch on `code` without
  string-matching `message`

**Acceptance criteria**:

- [ ] A call against a real running backend with no session returns the
      structured error shape, not a thrown parse error
- [ ] A call that gets a `401`, refreshes successfully, and retries,
      returns the retried call's result to the original caller
      transparently
- [ ] No page or component imports this yet — verified by grepping for
      the import outside `src/lib/`

---

### T-AUTH-5 — Frontend auth wiring

**Goal**: Replace the demo auth entirely with the real flow. This is the
task where `frontend-contract.md`'s Auth section actually gets retired.

**Scope** (confirm current state against T-AUTH-0's report before
starting):

- `AuthContext`: replace plain `useState` with a real session — call
  `GET /auth/me` on mount to bootstrap state (resolves
  `frontend-contract.md §1.2`'s "lost on reload" problem structurally,
  not by patching around it)
- `RegisterPage`/`registerSchema`: split `fullName` into `first_name` +
  `last_name` fields (`design.md §0` decision 5); wire the real submit to
  `POST /auth/register`; remove the fake `submitted`-then-discard flow
  (`frontend-contract.md §2.3`)
- `LoginPage`/`loginSchema`: rename `username` → `email` with email-format
  validation (`design.md §0` decision 6); remove `DEMO_USERNAME` /
  `DEMO_PASSWORD` and the "Continue as User/Admin" demo buttons entirely
  (`frontend-contract.md §2.2`'s Path A and Path B both go); wire the real
  submit to `POST /auth/login`; unify the post-login destination (the
  contract flagged Path A and B disagreeing on `/requests/new` vs `/` —
  pick one, `/` is reasonable, and there's only one path now so the
  disagreement resolves itself)
- Add a sign-out control calling `POST /auth/logout` — `AppShell`
  currently has none (`frontend-contract.md §2.1`)

**Explicitly out of scope for this task**: `frontend-contract.md §1.6`'s
missing `routes.tsx` / route guard. Nothing in the Auth requirements
depends on route guarding existing — it's a real gap, but a separate
concern from wiring auth itself. Flag it, don't fix it here.

**Acceptance criteria**:

- [ ] Registering through the UI creates a real user (verify via a
      backend query or the login flow immediately after)
- [ ] Logging in with wrong credentials shows one error message (matching
      `AUTH-7`'s non-distinguishing behavior) — UI-level confirmation of a
      backend guarantee
- [ ] Reloading the page after login preserves the session (via
      `GET /auth/me`, not in-memory state)
- [ ] No reference to `DEMO_USERNAME`, `DEMO_PASSWORD`, or the demo role
      buttons remains anywhere in the diff

---

**Group 1 checkpoint**: Auth end-to-end — backend and frontend both —
reviewed and working before Group 2 starts, per the agreed vertical-slice
process.

---

## Group 2 — Service Requests

### T-SR-0 — Backend service request endpoints

**Covers**: `SR-1` through `SR-13`.

**Scope**: `GET /service-requests` (list, filters, ownership scoping),
`POST /service-requests`, `GET /service-requests/{id}`. Depends on
T-AUTH-2's dependencies (`get_current_user`) for all three.

**Acceptance criteria**:

- [ ] `SR-1`/`SR-2`: a `user`-role caller sees only their own requests; an
      `admin`-role caller sees all
- [ ] `SR-3`/`SR-4`: valid `status`/`priority` filters narrow correctly;
      invalid values return `422`
- [ ] `SR-6` through `SR-10`: create validates all three fields, ignores
      client-supplied `request_type`/`requestor_id`/`current_status_id`,
      and the created row's `current_status_id` actually points at the
      `'open'` status
- [ ] `SR-11`/`SR-12`: a non-owner non-admin `GET`ting another user's
      request gets `404`, not `403`

### T-SR-1 — Frontend service request integration

**Scope** (confirm current state first, same discipline as T-AUTH-0):
`RequestsDashboardPage`, `SubmitRequestPage`, `RequestDetailsPage` switch
from importing `mockRequests`/`mockRequestDetail` to calling the real API
via `src/lib/api.ts`. Add loading and empty states — both are currently
absent (`frontend-contract.md §8.2`, §8.4) and now matter because data is
async and can genuinely be empty for a new user.

**Acceptance criteria**:

- [ ] Dashboard renders real requests for the logged-in user, empty state
      when there are none
- [ ] Submitting the form creates a real request and it appears in the
      dashboard afterward (closes the prototype's gap at
      `frontend-contract.md §8.7` where submission never touched the list)
- [ ] Detail page 404s visibly (not silently rendering wrong data) for an
      id the current user can't access — closes `frontend-contract.md
    §3.7`'s "always the same object regardless of `:id`" gap

**Group 2 checkpoint** before Group 3.

---

## Group 3 — Comments

### T-CM-0 — Backend comment endpoints

**Covers**: `CM-1` through `CM-9`.

**Acceptance criteria**:

- [ ] `CM-2`/`CM-3`: a `user`-role caller never receives an
      `is_internal: true` comment in the response body (check the raw
      JSON, not just what a UI would render)
- [ ] `CM-7`: a `user`-role caller posting `is_internal: true` gets `403`
      and no row is created
- [ ] `CM-8`: an `admin`-role caller can post with `is_internal: true`

### T-CM-1 — Frontend comment integration

**Scope**: `RequestDetailsPage` fetches comments from the real endpoint
instead of the embedded `comments` array. This also means building a
comment composer UI that **doesn't exist yet** — `frontend-contract.md
§6.5` documents its absence as deliberate for the prototype phase; that
phase is over. Include an `is_internal` checkbox, rendered only for
admin-role users (`CM-7`/`CM-8`).

**Acceptance criteria**:

- [ ] Comments list renders keyed by real `id`, not array index
      (closes `frontend-contract.md §6.4`)
- [ ] A regular user never sees the internal-comment checkbox in the DOM
      (not just hidden via CSS — absent)
- [ ] Posting a comment appends it to the visible list without a full
      page reload

**Group 3 checkpoint** before Group 4.

---

## Group 4 — Status history

### T-SC-0 — Backend status-change endpoints

**Covers**: `SC-1` through `SC-8`.

**Acceptance criteria**:

- [ ] `SC-3`: response contains only real `status_history` rows — write a
      test asserting the count equals actual transitions made, never a
      fixed number
- [ ] `SC-4`: a `user`-role caller `POST`ing a status change gets `403`
- [ ] `SC-5`/`SC-6`: the history-insert and `current_status_id`-update
      happen atomically — test by forcing a failure mid-transaction (e.g.
      an invalid `status_id` after a valid one in sequence) and asserting
      neither write landed, matching `backend/CLAUDE.md`'s testing
      convention of proving a test can actually fail

### T-SC-1 — Frontend status history integration

**Scope**: `RequestStatusPage` merges `GET /statuses` (all four, ordered)
against `GET /service-requests/{id}/status-changes` (only real
transitions) to reconstruct the filled/hollow-step visual —
this is the client-side merge described in `design.md §3`; it replaces
the prototype's fixed five-row template with `null` placeholders entirely
(`frontend-contract.md §7.2`). Add an admin-only status-change control
(select a status, optional note, submit) — doesn't exist in the prototype.

**Acceptance criteria**:

- [ ] A request with two real transitions shows two filled steps and the
      remaining seeded statuses hollow, in `sort_order`
- [ ] A regular user sees no status-change control in the DOM
- [ ] Posting a status change (as admin) updates the stepper without a
      full reload

**Group 4 checkpoint. All four vertical slices integrated — capstone API
layer complete.**
