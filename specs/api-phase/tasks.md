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
  other model needed already exists from the ORM phase. Confirmed through
  `T-SR-0`.
- **Completed-task writeups live in `task-log.md`, not here.** Each task
  below keeps only what a session needs before starting — Goal, Covers,
  Scope, Acceptance criteria — with a one-line pointer where a
  retrospective used to sit. The full account of what actually happened
  (mutation-pass results, spec corrections, defects found in the tests
  themselves) lives in `task-log.md` under the same task ID. Split at the
  Group 2 checkpoint, once this file passed 1,100 lines with 6 of 14 tasks
  still ahead of it — read `task-log.md` for the reasoning behind a past
  decision; this file is what a new task needs before starting, not a
  history of the project. When a task's own report contains something a
  _later_ task needs to know before it starts, that goes in the later
  task's Scope directly (see `T-SC-1`'s note on `RequestStatusPage`'s
  heading, for example) — never left for the later task to dig out of the
  log itself.

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

- [x] A short written diff-from-contract report, not a rewrite of the
      contract document itself
- [x] No files modified

**Stop here.** Review the report before starting T-AUTH-1 — if drift is
significant, the later Auth tasks in this group may need their acceptance
criteria adjusted first.

**Complete.** See `task-log.md#t-auth-0`.

---

### T-AUTH-1 — Backend auth utilities

**Goal**: Password hashing and JWT helpers, with no endpoints wired yet —
this is the foundation the next two tasks build on.

**Covers**: supports `AUTH-1` through `AUTH-15` indirectly (no requirement
IDs are independently testable at this layer — that's expected, this is
infrastructure).

**Scope**:

- Password hashing (`bcrypt` directly — **not** `passlib[bcrypt]`; passlib
  1.7.4 is unmaintained and its backend probe breaks against bcrypt ≥4.1,
  raising `ValueError` on every hash call. Confirmed during `T-AUTH-1`,
  rationale recorded in `security.py`'s docstring. Still "equivalent" per
  this task's original scope, just naming the specific library now that
  it's settled) — hash on register, verify on login. Never store or log a
  plaintext password. Export a `MAX_PASSWORD_BYTES` constant (72, bcrypt's
  hard limit) for the register schema to validate against (`AUTH-16`).
- JWT encode/decode helpers matching the claims shape in `design.md §1`
  (`sub`, `role`, `iat`, `exp`, `jti`).
- Cookie-setting helpers for access token (1 hr) and refresh token
  (30 day), `httpOnly` / `Secure` / `SameSite=Lax`, per `design.md §1` and
  `AUTH-6`. Also a `clear_auth_cookies` helper alongside the setters —
  `AUTH-12` (logout) needs matching attributes to actually clear them, and
  that logic belongs in the same module as the setters, not split out.
- Refresh-token hashing (store the hash in `refresh_tokens.token_hash`,
  never the raw token) and a lookup/verify helper.

**Acceptance criteria**:

- [x] Unit tests: a hashed password verifies correctly and a wrong
      password fails verification
- [x] Unit tests: a JWT round-trips (encode then decode yields the same
      claims) and an expired/tampered token fails decode
- [x] No endpoint routes added in this task

**Complete.** See `task-log.md#t-auth-1`.

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

- [x] `XC-4`: a request with an invalid field returns the custom envelope,
      not FastAPI's default shape
- [x] `XC-5`: a protected route with no cookie returns `401` in the
      correct envelope
- [x] `XC-6`: a `require_role("admin")` route hit by a `user`-role token
      returns `403`
- [x] `XC-9`: a `POST` with no `X-Requested-With` header returns `403`
      before any route logic runs
- [x] No auth _endpoints_ added yet — this is middleware only, exercised
      via a minimal throwaway test route if there's nothing real to hang
      it on yet
- [x] `XC-14`: **added on later review** — an unhandled exception (not a
      validation error, not an `HTTPException`) returns `500` in the
      envelope shape, with a generic message that provably doesn't leak
      the real exception's text. Verified: the handler already existed and
      was already tested from `T-AUTH-2`'s original work — the gap was
      that no requirement ID or acceptance line made it visible to a
      reviewer, not that it was missing. Coverage was then extended to all
      four exception origins (route body, dependency, response
      serialization, middleware stack), plus file-path leakage, raw-
      fallback-response shape, and operator-side traceback logging.

**Complete.** See `task-log.md#t-auth-2`.

---

### T-AUTH-3 — Auth endpoints

**Goal**: The five real endpoints, built on T-AUTH-1 and T-AUTH-2.

**Covers**: `AUTH-1` through `AUTH-16`, `XC-12`, `XC-13`, `XC-15`.

**Prerequisite check (not a new step — already done in `T-AUTH-2`)**:
confirm `db_session` is in a top-level `tests/conftest.py` and visible to
`tests/api/`. If it's still only in `tests/db/conftest.py`, that's a
regression to fix, not this task's original promotion work to redo.

**Scope**: Implement in this order (each depends on the last):

1. `POST /auth/register` — `AUTH-1` through `AUTH-5`, `AUTH-16` (the
   password-max-length check uses `security.py`'s exported
   `MAX_PASSWORD_BYTES` — don't re-hardcode `72` in the Pydantic schema)
2. `POST /auth/login` — `AUTH-6` through `AUTH-8`
3. `GET /auth/me` — `AUTH-14`, `AUTH-15` (simplest protected route, good
   smoke test for T-AUTH-2's dependency)
4. `POST /auth/refresh` — `AUTH-9` through `AUTH-11`
5. `POST /auth/logout` — `AUTH-12`, `AUTH-13`
6. Wire CORS middleware (`XC-12`) — `FRONTEND_ORIGIN` from config, explicit
   origin (never a wildcard), `allow_credentials=True`. Backend-only work,
   belongs here since this is the last backend-only task before `T-AUTH-4`
   needs it working; nothing in steps 1–5 depends on it, but `T-AUTH-4`
   silently fails without it.

**Test-writing gotcha, flagged by `T-AUTH-2`'s report**: the
cookie-persisting client fixture must use `base_url="https://testserver"`,
not an `http://` base — the auth cookies are `Secure`, and `httpx` drops
`Secure` cookies silently against a non-`https` base URL. Get this wrong
and the register → login → authenticated-call sequence fails in a way
that looks exactly like a broken auth flow, not a test-harness config
issue — worth getting right the first time rather than debugging it as a
mystery later.

**Acceptance criteria** (contract tests, real Postgres, per
`backend/CLAUDE.md`'s testing convention):

- [x] `AUTH-1`: valid register creates a `user`-role row, returns `201`,
      no cookies set
- [x] `AUTH-2`: duplicate email returns `409`
- [x] `AUTH-4`: a `role` field in the register body is ignored, not
      applied
- [x] `AUTH-5`/`XC-15`: no response body anywhere contains `password` or
      `password_hash` — **including error responses**, not just `2xx`.
      `T-AUTH-2`'s review surfaced that a `response_model` serialization
      failure carries the offending value inside
      `ResponseValidationError`, so the `500` path is a real leak vector
      for exactly the field `response_model` was excluding. The generic
      handler already covers this; add a test that would catch a
      regression on `/auth/register` or `/auth/me` specifically, since
      those are the endpoints where a `User` row is the serialization
      source
- [x] `AUTH-3`: an 11-character password returns `422`; a 12-character
      all-lowercase password with no digit or symbol succeeds — confirms
      the rule is length-only, not silently composition-gated
- [x] `AUTH-16`: a password over 72 bytes returns `422` with
      `fields.password` populated — not a `500`; include a case with a
      multi-byte-character password under 72 characters but over 72 bytes
- [x] `AUTH-6`: valid login sets both cookies with correct attributes and
      expiries
- [x] `AUTH-7`: wrong email and wrong password produce byte-identical
      error bodies
- [x] `AUTH-9`: refresh rotates the token (old row `revoked_at` set, new
      row inserted) and issues new cookies
- [x] `AUTH-11`: replaying an already-rotated refresh token revokes the
      rest of that user's active refresh tokens
- [x] `AUTH-12`/`AUTH-13`: logout is idempotent, always `204`
- [x] `XC-12`: a preflight `OPTIONS` and a real request from
      `FRONTEND_ORIGIN` both succeed with credentials; a request from an
      arbitrary other origin is rejected by CORS. **Also test a failing
      request** (e.g. bad credentials against `/auth/login`) from
      `FRONTEND_ORIGIN` — confirm the `401` response still carries the
      CORS headers, not just `2xx` responses. This is the specific gotcha
      that silently breaks a frontend's ability to read error bodies from
      cross-origin calls if missed.
- [x] `XC-13`: a user deactivated (`is_active = false`) after their token
      was issued is rejected `401` on their very next request, not only
      after the token's natural expiry — confirms the DB lookup is
      actually happening, not just present in the code path

**Complete.** See `task-log.md#t-auth-3`.

---

**Group 1 backend half complete.** `T-AUTH-4` and `T-AUTH-5` are the
frontend half of this same vertical slice; the group checkpoint comes
after `T-AUTH-5`, not here.

---

### T-AUTH-4 — Frontend API client

**Goal**: The `src/lib/api.ts` fetch wrapper described in this file's
conventions section — no page changes yet.

**Scope**:

- `credentials: 'include'` on every call
- `X-Requested-With` header on every non-`GET` call
- On a `401` from any call **except** `/auth/refresh` and `/auth/login`,
  attempt one silent `POST /auth/refresh`, then retry the original call
  once; if the refresh also fails, surface the original `401` to the
  caller. `/auth/login` is excluded because it reads no cookie at all — a
  refresh can never change whether a password is correct, and firing one
  there would needlessly rotate an already-signed-in user's tokens on
  someone else's failed sign-in attempt. (`T-AUTH-4` deviated from this
  file's original wording here and was right to; corrected in place.)
- **Concurrent `401`s must produce exactly one refresh**, not one per
  call. A shared in-flight promise alone is _not_ sufficient: a `401`
  that arrives just after a refresh settles was generated against the
  already-replaced token, and retrying it starts a second refresh. Track
  a session generation counter instead — a call captures it before
  sending, and a `401` carrying a superseded generation retries directly
  without refreshing again. This matters because `AUTH-9`'s single-use
  rotation plus `AUTH-11`'s family revocation means a redundant refresh
  presenting a rotated token gets the user signed out of everything, for
  doing nothing wrong.
- A typed error shape matching the `error.code` / `error.message` /
  `error.fields` envelope, so calling code can branch on `code` without
  string-matching `message`

**Acceptance criteria**:

- [x] A call against a real running backend with no session returns the
      structured error shape, not a thrown parse error
- [x] A call that gets a `401`, refreshes successfully, and retries,
      returns the retried call's result to the original caller
      transparently
- [x] No page or component imports this yet — verified by grepping for
      the import outside `src/lib/`

**Complete.** See `task-log.md#t-auth-4`.

---

### T-AUTH-5 — Frontend auth wiring

**Goal**: Replace the demo auth entirely with the real flow. This is the
task where `frontend-contract.md`'s Auth section actually gets retired.

**Scope** (confirm current state against T-AUTH-0's report before
starting):

- `AuthContext`: replace plain `useState` with a real session — call
  `GET /auth/me` on mount to bootstrap state (resolves
  `frontend-contract.md §1.2`'s "lost on reload" problem structurally,
  not by patching around it). The context's shape widens from `role`
  alone to the full `/auth/me` response (`id`, `first_name`, `last_name`,
  `role`) — note `§1.5`'s finding that zero components currently consume
  `role`, so this is a clean widen with nothing to migrate
- `RegisterPage`/`registerSchema`: split `fullName` into `first_name` +
  `last_name` fields, named exactly that (`snake_case`, per
  `frontend/CLAUDE.md`'s Naming exception for API-shaped schemas —
  `design.md §0` decision 5), each 1–100 chars. `password`: min 12 chars
  (`AUTH-3`) — **length only, no composition regex** (no required
  uppercase/digit/symbol). This was decided deliberately during spec
  review, not left unspecified — don't add a composition regex "to be
  thorough"; that's reintroducing a rule that was considered and rejected,
  not filling a gap. For a max: `AUTH-16`'s real limit is 72 `_bytes_`, not
  characters, so a client-side `.max(72)` on string length is a false
  guarantee (an emoji-heavy password can clear that char count and still
  fail server-side). Either measure bytes client-side too (`new
TextEncoder().encode(password).length`) or skip a client max entirely
  and let the server's `422` be the sole authority — don't ship a
  client-side check that gives false confidence. The prototype's register
  form has never had a max length on any field; against the real API
  that's a gap to close, not a style preference. `confirmPassword` stays
  client-only validation — it has no backend counterpart and must never be
  included in the `POST /auth/register` body; wire the real submit to
  `POST /auth/register`; remove the fake `submitted`-then-discard flow
  (`frontend-contract.md §2.3`) — note the current `onValidSubmit` doesn't
  even bind its parameter, so this is a real rewrite of that handler, not
  a small edit to it
- `LoginPage`/`loginSchema`: rename `username` → `email` with email-format
  validation (`design.md §0` decision 6); remove `DEMO_USERNAME` /
  `DEMO_PASSWORD` and the "Continue as User/Admin" demo buttons entirely
  (`frontend-contract.md §2.2`'s Path A and Path B both go — this also
  strands the `Role` type import, currently used only to type
  `continueAs`; remove that import in the same edit, not as a follow-up
  lint fix); unify the post-login destination (the contract flagged Path A
  and B disagreeing on `/requests/new` vs `/` — pick one, `/` is
  reasonable, and there's only one path now so the disagreement resolves
  itself); wire the real submit to `POST /auth/login`; render the
  server's `error.message` on failure (`AUTH-7`) instead of the current
  hardcoded `"Incorrect username or password"` string — the real message
  is worded differently (`"Incorrect email or password."`), and per
  `frontend/CLAUDE.md`'s Error surfacing section this should come from the
  response, not a local constant, even where the two happen to say
  something similar
- Both forms: disable the submit button for the duration of the in-flight
  request, not just after success. `RegisterPage`'s existing
  `disabled={submitted}` was a harmless cosmetic gap against fake
  submission (`frontend-contract.md §8.2`) — against a real network call
  it now permits genuine double-submission, so this is a correctness fix,
  not polish
- Extract the `Field` wrapper component, currently duplicated
  byte-for-byte across `LoginPage` and `RegisterPage`
  (`frontend-contract.md §8.3`). Both pages are being edited in this task,
  which is exactly the condition `frontend/CLAUDE.md`'s Error surfacing
  section names as the trigger to extract it here rather than defer it
- Add a sign-out control calling `POST /auth/logout` — `AppShell`
  currently has none (`frontend-contract.md §2.1`)

**Explicitly out of scope for this task**: `frontend-contract.md §1.6`'s
missing `routes.tsx` / route guard. Nothing in the Auth requirements
depends on route guarding existing — it's a real gap, but a separate
concern from wiring auth itself. Flag it, don't fix it here.

**Acceptance criteria**:

- [x] Registering through the UI creates a real user (verify via a
      backend query or the login flow immediately after)
- [x] Logging in with wrong credentials shows one error message (matching
      `AUTH-7`'s non-distinguishing behavior), rendered from
      `error.message` in the response — UI-level confirmation of a
      backend guarantee, not a hardcoded local string
- [x] Reloading the page after login preserves the session (via
      `GET /auth/me`, not in-memory state)
- [x] No reference to `DEMO_USERNAME`, `DEMO_PASSWORD`, the demo role
      buttons, or the now-unused `Role` type import remains anywhere in
      the diff
- [x] Both submit buttons are disabled for the duration of their request,
      not only after success
- [x] `Field` exists as one shared component imported by both pages, not
      duplicated
- [x] `confirmPassword` never appears in the network request body sent to
      `POST /auth/register`

**Complete.** See `task-log.md#t-auth-5`.

---

### T-DEBT-1 — Retire the third `Field` copy

**Do this as part of `T-SR-1`**, which opens `SubmitRequestPage` anyway —
not as a standalone task. One-line import swap plus deleting the local
copy.

Why it's tracked rather than left as a report note: `frontend/CLAUDE.md`'s
extract-when-you-touch-two-pages rule was satisfied literally by
`T-AUTH-5`, but its _purpose_ — one `Field`, not three — isn't met while a
third copy survives. A later edit to `Field.tsx` would silently not apply
to `SubmitRequestPage`, which is exactly the failure mode the rule exists
to prevent.

**Done** — folded into `T-SR-1`; see that task's acceptance criteria.

---

### T-DEBT-2 — Route guard

**Decided at the Group 1 checkpoint: build it now**, before `T-SR-0`.
Rationale: `T-SR-1` makes the dashboard fetch real data, at which point a
signed-out user gets a page of `401` errors instead of a login redirect.
Building the guard first means Group 2's frontend task lands on a correct
signed-out experience rather than creating a broken one and fixing it
after.

**Scope**:

- Create `src/routes.tsx` — the file `frontend/CLAUDE.md` has documented
  since the prototype phase but which was never built (Task 3 debt). Move
  the inline route table out of `App.tsx` into it.
- A guard component that redirects to `/login` when there is no session.
  `/login` and `/register` are public; every other route requires a
  session.
- **Handle the three-state session correctly.** `AuthContext` bootstraps
  via `GET /auth/me`, so on first mount the session is _pending_ — neither
  known-present nor known-absent. If the guard treats pending as
  signed-out, a signed-in user reloading any page gets bounced to `/login`
  before the bootstrap resolves, then bounced back. Render nothing (or a
  minimal loading state) while pending; only redirect once the answer is
  actually known. This is the single most likely way to get this task
  wrong.
- Add the `path="*"` catch-all route that
  `frontend-contract.md §8.5` flags as missing — an unmatched URL
  currently renders nothing at all.
- Fix `AppShell`'s nav to use router `<Link>` rather than plain
  `<a href>` (`frontend-contract.md §8.6`/§9-#17). With cookie-based auth
  a full reload no longer wipes the session, so this is no longer a
  correctness bug — but it still costs a full page reload plus a
  redundant `/auth/me` round-trip on every nav click.

**This guard is cosmetic, and must be commented as such** where it's
implemented. Every real authorization check is server-side (`XC-6`,
`XC-13`, `SR-1`, `SC-4`, `CM-7`) — the guard improves the signed-out
experience and nothing more. Do not let its existence become a reason
anyone later trusts it as an access control.

**Acceptance criteria**:

- [x] Signed out, visiting `/` redirects to `/login` rather than
      rendering the shell
- [x] Signed in, a hard reload of `/` stays on `/` — no flash of
      `/login` while `GET /auth/me` is in flight
- [x] `/login` and `/register` remain reachable while signed out
- [x] An unmatched URL renders a not-found page, not a blank screen
- [x] `AppShell` nav uses `<Link>`; clicking it does not trigger a full
      page reload (verify in the network tab — no document request)
- [x] The guard's cosmetic-only nature is commented at its definition

**Complete.** See `task-log.md#t-debt-2`.

---

### T-DEBT-3 — Playwright harness

**Decided at the Group 1 checkpoint: stand it up now**, after `T-DEBT-2`
so the guard is included, and before `T-SR-0` so Group 2's frontend work
lands on an existing harness rather than adding to an untested pile.

Rationale: the backend has 147 tests and the frontend has none. Both
`T-AUTH-4` and `T-AUTH-5` were verified live in a browser — good evidence,
but one-time, with nothing guarding regressions. The riskiest logic in the
slice (`api.ts`'s refresh-concurrency rule) has no automated coverage at
all, and it's the kind of thing a well-meaning future refactor would
simplify straight back into a bug.

**Why Playwright and not a mocked unit test**: the behavior that matters
here is inseparable from real cookies, real CORS, and a real backend —
`httpOnly` cookies are invisible to JavaScript by design, so a mocked
client can't meaningfully exercise them. `frontend/CLAUDE.md` also rules
out MSW. Playwright against the running stack tests the thing itself.

**Scope**:

- Playwright installed and configured; a script that runs the suite
  against the dev servers.
- A seeding approach for test users — either a fixture that registers a
  fresh user per run (self-contained, slower) or a documented seeded
  account. Prefer per-run registration: tests that depend on a manually
  maintained account rot silently.
- Cover the Auth slice's behavior, not its implementation:
  - register → login → reload → session persists
  - wrong password and unknown email produce identical error text
    (`AUTH-7` — the guarantee most easily undone by a future UI edit)
  - logout ends the session server-side (a reload does not restore it)
  - **concurrent `401`s produce exactly one `/auth/refresh`** — the
    `T-AUTH-4` finding; assert on the network requests, not on internal
    state
  - signed-out access to a protected route redirects to `/login`
    (`T-DEBT-2`)

**Acceptance criteria**:

- [x] The suite runs green against the running stack from a single
      documented command
- [x] The refresh-concurrency test fails if the `sessionGeneration` guard
      in `api.ts` is removed — verify by actually removing it, confirming
      red, and restoring. Per `backend/CLAUDE.md`'s rule, a test never
      observed to fail is not verified, only written; that applies here
      too
- [x] The `AUTH-7` test fails if the login page is changed to
      distinguish wrong-password from unknown-email
- [x] No test depends on a hand-maintained database row

**Complete.** See `task-log.md#t-debt-3`.

---

**Group 1 complete — Auth end-to-end.** See `task-log.md#group-1-checkpoint`
for what the slice validated and the two checkpoint decisions it produced.

---

## Group 2 — Service Requests

### T-SR-0 — Backend service request endpoints

**Covers**: `SR-1` through `SR-15`, `ST-1`, `ST-2`.

**Scope**: `GET /statuses`, `GET /service-requests` (list, filters,
ownership scoping), `POST /service-requests`,
`GET /service-requests/{id}`. Depends on T-AUTH-2's dependencies
(`get_current_user`) for the three service-request routes; `GET
/statuses` is public per `ST-1`.

`GET /statuses` was folded in here during spec review: `ST-1`/`ST-2` were
owned by no task at all (Group 2 covered `SR-*`, Group 3 `CM-*`, Group 4
`SC-*`), while `T-SC-1` assumed the endpoint existed. It also belongs
here practically — `StatusOut` is built this task anyway as the embedded
status object on every `ServiceRequest`, and `T-SR-1`'s filter dropdown
needs the endpoint.

**Acceptance criteria**:

- [x] `ST-1`/`ST-2`: `GET /statuses` needs no session, returns all four
      seeded rows ordered by `sort_order`, as a bare `{"items": [...]}`
      and not the paginated envelope
- [x] `SR-1`/`SR-2`: a `user`-role caller sees only their own requests; an
      `admin`-role caller sees all — asserted on specific ids, with both
      sides non-empty (a test where both fixtures own zero rows passes
      vacuously)
- [x] `SR-1` + `XC-10`: `total` reflects the scoped count, not the table
      count
- [x] `SR-3`/`SR-4`: valid `status`/`priority` filters narrow correctly;
      invalid values return `422` (an unseeded status name is a `422`
      with `fields.status`, never a silently empty `200`)
- [x] `SR-5`: every list item carries `description`
- [x] `SR-15`: ordering is `created_at DESC, id DESC`, stable across
      repeated calls on rows sharing a `created_at`
- [x] `XC-10`/`XC-11`: `page_size=250` returns a `200` reporting
      `page_size` 100, not a `422`
- [x] `SR-6` through `SR-9`: create validates all three fields at their
      boundaries (at the limit and one over)
- [x] `SR-10`/`XC-8`: a body carrying `request_type`, `requestor_id`, and
      `current_status_id` succeeds with all three ignored — the created
      row is the caller's, `general`, and `open`
- [x] `SR-14`: creation inserts exactly one `status_history` row pointing
      at `open` with `changed_by_id` = the caller; forcing that insert to
      fail leaves no `service_requests` row behind
- [x] `SR-11`/`SR-12`/`SR-13`: owner and admin get `200`; non-owner
      non-admin, absent UUID, and malformed id all return `404` with
      byte-identical bodies
- [x] `AUTH-5`/`XC-15`: no response body on these endpoints contains
      `password` or `password_hash`, error responses included
- [x] N+1: statement count is _equal_ for 3 rows and 15 rows, not merely
      below a threshold

**Complete.** See `task-log.md#t-sr-0`.

---

### T-DEBT-4 — Two missing tests on the service-request routes

**Do this as part of `T-CM-0`**, not as a standalone task — both tests
are also the template `T-CM-0` and `T-SC-0` should follow, so writing
them there costs almost nothing and immediately gets reused.

Neither is likely to be broken today. Both are in the project's recurring
failure family — a green suite that doesn't actually assert the thing it
appears to:

1. **A `401`-when-unauthenticated test on each of the three
   `/service-requests` routes.** `XC-5` was proven in `T-AUTH-2` against a
   throwaway route. Every `T-SR-0` test uses an authenticated client, so
   a route declared without `get_current_user` would only break by side
   effect — true here because the handlers need the user for scoping, and
   _not_ true of routes where the user is used only for a visibility
   check, which Groups 3 and 4 both have.
2. **A `total`-respects-filters assertion.** `T-SR-0` proved `total` is
   the _scoped_ count. If the `COUNT` query applies the scope predicate
   but not the `status`/`priority` filter predicates, every item-level
   assertion still passes and only a filtered-list `total` catches it —
   one predicate over from the bug the scoping mutation did catch.

---

### T-SR-1 — Frontend service request integration

**Scope** (confirm current state first, same discipline as T-AUTH-0):
`RequestsDashboardPage`, `SubmitRequestPage`, `RequestDetailsPage` switch
from importing `mockRequests`/`mockRequestDetail` to calling the real API
via `src/lib/api.ts`. Add loading and empty states — both are currently
absent (`frontend-contract.md §8.2`, §8.4) and now matter because data is
async and can genuinely be empty for a new user.

**This task establishes the loading and empty-state pattern for the whole
phase.** `frontend/CLAUDE.md` is explicit that it gets invented once,
here, and reused by Groups 3 and 4 — `T-DEBT-2` deliberately rendered
`null` while pending rather than inventing a spinner first. Don't leave a
second pattern behind. Build it as a discriminated union, not a boolean:

```ts
type Async<T> =
  | { status: "pending" }
  | { status: "error"; error: ApiError }
  | { status: "ready"; data: T };
```

A boolean `isLoading` plus nullable `data` plus nullable `error` permits
combinations that are nonsense (loading _and_ data _and_ error) and
relies on render-order convention to stay safe — the same failure shape
`T-DEBT-2` hit by collapsing a three-state session into a boolean. Empty
is **not** a fourth member: it's `ready` with an empty array, and the
dashboard branches on length — a new user's empty list is a legitimate
state, not an error. Put the shared type in one place under `src/` and
use it on all three pages; a second shape appearing on any of them is a
sign this wasn't actually established, only described.

**Every effect that sets state from an async call must invalidate its
in-flight result on cleanup** — an `AbortController` aborted in cleanup,
or an `ignore` flag checked before `setState`. The dashboard's filters
make this reachable in normal use, not just in theory: change a filter
twice quickly and an earlier response landing after a later one wins,
showing results that contradict the controls. Same family as
`T-AUTH-4`'s `sessionGeneration` finding — "was this response produced by
a request I still care about?", decided at response handling, not
dispatch. It will not reproduce against localhost by accident; write it
correctly rather than waiting to observe it break.

Also in scope, from `T-SR-0`'s report:

- **`STATUS_CONFIG` in `StatusPill.tsx` must be updated** to the four
  backend values (`open`, `in_progress`, `resolved`, `closed`) with
  `draft` dropped, per `frontend/CLAUDE.md`'s Component conventions.
  Status names arrive from the API as raw identifiers (`in_progress`) —
  the display-label mapping is a frontend concern by `design.md §0`
  decision 4, and `STATUS_CONFIG` is where it already lives. Don't create
  a second mapping elsewhere.
- **Filter values must come from `GET /statuses`**, not a hardcoded array
  of four strings. `SR-3` returns a `422` for an unrecognised name, so a
  hardcoded list that drifts from the seed produces a broken filter
  rather than an empty result. `GET /statuses` requires no session
  (`ST-1`), so it can load before the auth bootstrap resolves. Priority
  options ARE hardcoded (`low`/`medium`/`high`) — that set is a fixed
  CHECK constraint (`SR-4`), not a lookup table, so the asymmetry with
  status is deliberate. The list and its filter dropdown are two
  independent async resources with independent failure modes: a slow or
  failed `/statuses` must never blank a request table that already
  arrived, and the two must not share one pending flag.
- The dashboard's date column shows and sorts by the **same** field:
  `created_at`, labelled "Submitted" — `SR-15` orders by `created_at
DESC`, and a column showing `updated_at` instead would make the list
  look mis-sorted.
- Pagination controls (prev/next, "Showing X–Y of N") driven by the
  `XC-10` envelope's `total`/`page`/`page_size` — without them a user
  past the default page size of 20 silently sees only the first page
  with nothing indicating more exist.
- **`assignee` is always `null` this phase** — there is no assignment
  path and `PATCH` is deferred (`design.md §7`). Render "Unassigned"
  everywhere rather than hiding the field or inventing a placeholder
  name. (The prototype's other hardcoded assignment string,
  `STATUS_HISTORY_LABELS`' `'Assigned to IT Service Desk'`, lives in the
  status timeline and is `T-SC-1`'s to retire — don't half-fix it here.)
- **Decide the admin dashboard copy.** `SR-2` gives an admin every
  request, and the nav has exactly one dashboard item, so an admin
  loading a page headed "My Requests" sees everyone's. That's a lie in
  the UI, not a backend gap: fix it with role-dependent heading and
  empty-state text on the one page. Do **not** add a "My requests / All
  requests" toggle or a `?requestor_id=me` param — no designed surface
  consumes them, and they'd arrive without a consumer.
- Timestamps arrive as ISO 8601 UTC (`XC-2`), replacing the prototype's
  pre-formatted strings — one formatting helper module, used everywhere,
  rendering inside `<time dateTime={iso}>`. `Intl.DateTimeFormat` covers
  this; no date library needed.

**Acceptance criteria**:

- [x] Dashboard renders real requests for the logged-in user, empty state
      when there are none
- [~] No page imports from `src/data/`; the retired fixture files are
  deleted — **partially met, deliberately.** `mockRequests.ts` and
  `mockRequestDetail.ts` are deleted. `mockStatusHistory.ts` survives
  because `RequestStatusPage` is `T-SC-1`'s to convert; see
  `task-log.md#t-sr-1`
- [x] `T-DEBT-1`: `SubmitRequestPage` imports the shared `Field.tsx` and
      its local copy is deleted — no `Field` definition survives outside
      `components/ui/Field.tsx`
- [x] Submitting the form creates a real request and it appears in the
      dashboard afterward (closes the prototype's gap at
      `frontend-contract.md §8.7` where submission never touched the list)
- [x] Submit button disabled for the duration of the request, not only
      after success (same correctness fix as `T-AUTH-5`)
- [x] Detail page 404s visibly (not silently rendering wrong data) for an
      id the current user can't access — closes `frontend-contract.md
§3.7`'s "always the same object regardless of `:id`" gap
- [x] `STATUS_CONFIG` carries exactly the four backend statuses; `draft`
      appears nowhere in the frontend
- [x] The status filter's options are fetched from `GET /statuses`, not
      hardcoded, and a slow/failed call doesn't block the request table
- [x] Rapid filter changes never leave the table showing results that
      contradict the controls (verify with a deliberately delayed
      response in a Playwright route handler; per `T-DEBT-3`'s finding,
      key the delay off something captured at handler entry, not a
      shared mutable counter read after an `await`)
- [x] Pagination controls reflect `total`/`page`/`page_size`; page 2 works
- [x] An admin and a regular user both see accurate heading and
      empty-state copy for what the list actually contains — verified
      live for both roles, with one variant unobservable; see
      `task-log.md#t-sr-1`
- [x] One formatting helper module; no pre-formatted date strings survive
      and no second formatter exists
- [x] Checked at ~1280px and ~375px, per `frontend/CLAUDE.md`
- [x] Playwright specs added for: dashboard empty state, create-then-see-
      on-dashboard, detail-page `404` for another user's request, and
      status filter options coming from the network — each verified by
      removing the behaviour and observing red, per `backend/CLAUDE.md`'s
      "a test never observed to fail is not verified" rule applied here
      too

**Complete.** See `task-log.md#t-sr-1`.

---

### T-DEBT-5 — Title cap and admin requestor column

**Decided at the Group 2 checkpoint**: two small, real gaps identified in
`T-SR-1` (`task-log.md#t-sr-1`), both cheap enough to close now rather
than carry forward with no later task naturally reopening these files —
same reasoning as bundling `T-DEBT-2`/`T-DEBT-3` at the Group 1
checkpoint.

**Scope**:

1. Raise `submitRequestSchema`'s `title` max from 100 to 200, matching
   `SR-7`. The 100 was a prototype-phase leftover; `SR-7`'s 200 is the
   real column limit, and unlike `description` there was never a
   documented two-tier UX-cap-below-a-backstop design for `title`
   (`design.md §4` is explicit about that split for `description` and
   silent on `title`). Update the validation error message to match.
2. Add a "Requestor" column to `RequestsDashboardPage`'s table, rendered
   only when the viewing user's role is `admin` (`SR-2` gives admins
   every request; a regular user's own name in every row would be
   redundant). Use each item's existing embedded `requestor` field — no
   new fetch, no backend change. Check this doesn't break the table at
   ~375px; collapse or hide the column there if the existing table
   pattern requires it.

**Acceptance criteria**:

- [x] A 150-character title is accepted (previously rejected at 100); a
      201-character title is still rejected with `fields.title` populated
- [x] `RequestsDashboardPage` shows a Requestor column when the viewer is
      `admin`; a regular user's view is unchanged — absent from the DOM,
      not CSS-hidden
- [x] Checked at ~1280px and ~375px

Report, then stop — `T-CM-0` is next.

**Complete.** See `task-log.md#t-debt-5`.

---

**Group 2 checkpoint** before Group 3.

---

## Group 3 — Comments

### T-CM-0 — Backend comment endpoints

**Covers**: `CM-1` through `CM-9`. Also completes `T-DEBT-4`.

**Acceptance criteria**:

- [ ] `CM-2`/`CM-3`: a `user`-role caller never receives an
      `is_internal: true` comment in the response body (check the raw
      JSON, not just what a UI would render)
- [ ] `CM-7`: a `user`-role caller posting `is_internal: true` gets `403`
      and no row is created
- [ ] `CM-8`: an `admin`-role caller can post with `is_internal: true`
- [ ] `T-DEBT-4`: a `401`-when-unauthenticated test exists for each of
      the three `/service-requests` routes and for both comment routes
- [ ] `T-DEBT-4`: `total` on a _filtered_ list reflects the filters, not
      just the visibility scope

### T-CM-1 — Frontend comment integration

**Scope**: `RequestDetailsPage` fetches comments from the real endpoint
instead of the embedded `comments` array. This also means building a
comment composer UI that **doesn't exist yet** — `frontend-contract.md
§6.5` documents its absence as deliberate for the prototype phase; that
phase is over. Include an `is_internal` checkbox, rendered only for
admin-role users (`CM-7`/`CM-8`). Reuse `T-SR-1`'s loading and
empty-state pattern (`src/lib/async.ts`, `AsyncSection` — see
`frontend/CLAUDE.md`'s Async state section); do not invent a second one.

**Acceptance criteria**:

- [ ] Comments list renders keyed by real `id`, not array index
      (closes `frontend-contract.md §6.4`)
- [ ] A regular user never sees the internal-comment checkbox in the DOM
      (not just hidden via CSS — absent)
- [ ] Requestor-column regression (T-DEBT-5 debt): two service requests
      with two different requestors show two different names in the
      admin dashboard's Requestor column, not the viewer's own name
      repeated. Manually verified in T-DEBT-5; never captured as an
      automated test until now.
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
      fixed number. Note `SR-14` means a freshly created request already
      has exactly one row (`open`), so the baseline is one, not zero
- [ ] `SC-4`: a `user`-role caller `POST`ing a status change gets `403`
- [ ] `SC-5`/`SC-6`: the history-insert and `current_status_id`-update
      happen atomically — test by forcing a failure mid-transaction (e.g.
      an invalid `status_id` after a valid one in sequence) and asserting
      neither write landed, matching `backend/CLAUDE.md`'s testing
      convention of proving a test can actually fail
- [ ] `SR-14`'s invariant still holds after a transition:
      `current_status_id` equals the status of the most recent
      `status_history` row, always

### T-SC-1 — Frontend status history integration

**Scope**: `RequestStatusPage` merges `GET /statuses` (all four, ordered)
against `GET /service-requests/{id}/status-changes` (only real
transitions) to reconstruct the filled/hollow-step visual —
this is the client-side merge described in `design.md §3`; it replaces
the prototype's fixed five-row template with `null` placeholders entirely
(`frontend-contract.md §7.2`). Add an admin-only status-change control
(select a status, optional note, submit) — doesn't exist in the prototype.

`SR-14` means the merge has a real first step to work with: a brand-new
request already has one genuine `open` transition, so no step needs
synthesising and no "the first step is always filled" special case
belongs anywhere in this code.

Also retire `STATUS_HISTORY_LABELS`' hardcoded
`'Assigned to IT Service Desk'` (`frontend-contract.md §7.4`/§3.5). The
whole five-state `StatusHistoryState` vocabulary
(`submitted`/`assigned`/...) goes with it — the backend has four
statuses and no `assigned` state, and there is no assignment data behind
that label at all (`assignee` is always `null` this phase). Deleting it
also resolves `frontend-contract.md §9-#8`, the two-non-matching-status-
enums inconsistency, since only `Status` survives. **When you delete this
vocabulary, grep for its literal string values across the whole tree, not
just typed usages** — `T-SR-1` found a retired status name surviving as
an untyped string in `src/lib/utils.ts`'s tailwind-merge class-group
config, invisible to a TypeScript usages search (`task-log.md#t-sr-1`).

`RequestStatusPage`'s heading currently shows the request id alone, with
no title — `T-SR-1` deliberately dropped it rather than fetch real
request data just to back a heading sitting above a still-fake timeline
(`task-log.md#t-sr-1`). This task wires the page to real data; restore
the title in the heading now that it isn't backing a fabrication.

**Acceptance criteria**:

- [ ] A request with two real transitions shows two filled steps and the
      remaining seeded statuses hollow, in `sort_order`
- [ ] A regular user sees no status-change control in the DOM
- [ ] Posting a status change (as admin) updates the stepper without a
      full reload
- [ ] `StatusHistoryState` and `STATUS_HISTORY_LABELS` no longer exist
      anywhere in the frontend, including as untyped string literals
- [ ] `RequestStatusPage`'s heading shows the real request title, not
      just the id

**Group 4 checkpoint. All four vertical slices integrated — capstone API
layer complete.**
