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

- [x] A short written diff-from-contract report, not a rewrite of the
      contract document itself
- [x] No files modified

**Stop here.** Review the report before starting T-AUTH-1 — if drift is
significant, the later Auth tasks in this group may need their acceptance
criteria adjusted first.

**Complete — zero drift found.** All five files matched
`frontend-contract.md` exactly. Findings folded into `T-AUTH-5`'s scope and
`frontend/CLAUDE.md` (the `routes.tsx` absence, the snake_case casing
decision) rather than left in this task's own notes.

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

**Complete.** 38 new tests, all passing, mutation-tested (14 deliberate
defects, all caught) per `backend/CLAUDE.md`'s "verify a test can actually
fail" rule. One real gap the mutation pass surfaced worth knowing about
generically, not just for this task: a tamper test that corrupts a token's
encoding (rather than its _meaning_) can pass for the wrong reason — it
fails before reaching the check you actually meant to test. Worth
remembering next time you write a tamper/corruption test anywhere in this
project: corrupt something that's still well-formed, or you're not testing
what you think you're testing.

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

**Complete.** 90 tests total (39 new), mutation-tested per the same
"verify it can fail" rule as `T-AUTH-1`. Corrections folded back into
`requirements.md`/`design.md` rather than left as implementation-only
notes: `XC-9` now exempts `HEAD`/`OPTIONS` (not just `GET`) and checks
header _presence_, not an exact value; a new `XC-12` covers CORS, which
was missing from the original spec entirely and would have silently
broken `T-AUTH-4`; `XC-4` now explicitly covers framework-raised errors
(an unmatched route), not only Pydantic validation failures.

Built via a `create_app()` factory in `main.py` — tests construct the same
app the server runs, not a hand-assembled lookalike that could drift from
it. `require_role` is rank-based against the two-role hierarchy (`XC-6`
already said "minimum required role" — this confirms the spec, doesn't
change it): an admin passes a `require_role("user")` gate.

**Resolved**: `get_current_user` loads the full user row from the database
on every protected request, rather than trusting the JWT's `role` claim
alone. This reverses `design.md`'s originally stated rationale for
embedding `role` in the token (avoiding a DB hit per request) — kept
deliberately, not by default; see the note below this task list for the
full tradeoff and the resulting `XC-13`.

`db_session` was promoted to a top-level `tests/conftest.py` during this
task already (this task's own tests needed it from `tests/api/`) — the
prerequisite originally written into `T-AUTH-3` below is done; that task
should verify it, not redo it.

**Resolved**: keep `get_current_user` loading the fresh user row on every
protected request (immediate effect for deactivation/deletion, free real
names for `/auth/me`) over reverting to trusting the JWT claims alone.
`design.md`'s JWT claims section and `requirements.md`'s new `XC-13`
carry the final wording — this note is kept only as a record that the
choice was made deliberately, not defaulted into.

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

**Complete.** 147 tests total (52 new), mutation-tested — 31 deliberate
defects, all caught. That pass found a real hole in the tests themselves:
the cookie-expiry assertion derived its expected value from the same TTL
constant it was testing, so changing the access token to 30 days kept it
green. Now pinned to literal `3600`/`2592000` from `AUTH-6`. Worth
generalizing: **a test that computes its expectation from the code under
test asserts only self-consistency, not correctness** — the same class of
error as `T-AUTH-1`'s tamper test passing for the wrong reason.

Three decisions folded back into the specs rather than left as
implementation notes: `AUTH-17` (email case-folding, previously
unspecified), the `design.md` logout contradiction fixed in favor of
`AUTH-13`'s idempotency, and `XC-12`'s documented `ServerErrorMiddleware`
exception for the `500` path. `AUTH-18` records the login-timing decoy
as a deliberate blind spot — implemented but not test-enforced, since a
wall-clock assertion would be flaky.

Also added `email-validator` to `requirements.txt` (Pydantic's `EmailStr`
needs it), and auth tests use `@example.com` rather than the DB fixtures'
`@example.test`, which `email-validator` rejects as a reserved TLD.

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

**Complete.** Verified in a real Chromium page against the running
backend, so `credentials: 'include'`, CORS, and the `httpOnly`/`Secure`
cookies were genuinely exercised rather than mocked — including the
`XC-12` error-path CORS behavior specced during `T-AUTH-3`, which is
exactly the thing a mocked test would have missed.

The concurrency finding is worth remembering past this task: deduping
concurrent refreshes with a shared in-flight promise **looks** correct
and isn't. A `401` landing just after a refresh settles was generated
against the already-replaced token; retrying it starts a second,
redundant refresh — which, given `AUTH-11`'s family revocation, is one
arrival-order shift away from signing the user out of everything. The fix
reframes the question from "is a refresh running?" to "was this `401`
produced by a token that's already been replaced?" — a stale-response
problem in concurrency clothing.

Exports are thin per-endpoint functions (`register`/`login`/`getMe`/
`logout`); the underlying wrapper stays module-private so `T-AUTH-5`
can't accidentally grow a second client alongside it.

Two dev-database users exist from this task's live testing
(`t-auth-4.<timestamp>@example.com`) — usable as seeded logins for
`T-AUTH-5`, or delete them.

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
  `last_name` fields, named exactly that (snake_case, per
  `frontend/CLAUDE.md`'s Naming exception for API-shaped schemas —
  `design.md §0` decision 5), each 1–100 chars. `password`: min 12 chars
  (`AUTH-3`) — **length only, no composition regex** (no required
  uppercase/digit/symbol). This was decided deliberately during spec
  review, not left unspecified — don't add a composition regex "to be
  thorough"; that's reintroducing a rule that was considered and rejected,
  not filling a gap. For a max: `AUTH-16`'s real limit is 72 _bytes_, not
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

**Complete.** Verified live in Chromium against the running backend.
`AUTH-7`'s non-enumeration guarantee now holds end-to-end: identical
banner text for a wrong password on a real account and for an
unregistered address — a backend guarantee that a careless UI could
easily have undone by distinguishing them at the presentation layer.

Error routing by status is working as designed: a `422` lands inline on
the offending field via `fields`, a `409` surfaces as a page-level banner
because `ConflictError` deliberately carries no `fields` map. That split
is the `error.code`-not-`error.message` branching rule paying off.

**Carried debt out of this task** (both tracked below, neither blocking):
`SubmitRequestPage` still holds its own local `Field` copy, and routes
remain unguarded.

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

- [ ] Signed out, visiting `/` redirects to `/login` rather than
      rendering the shell
- [ ] Signed in, a hard reload of `/` stays on `/` — no flash of
      `/login` while `GET /auth/me` is in flight
- [ ] `/login` and `/register` remain reachable while signed out
- [ ] An unmatched URL renders a not-found page, not a blank screen
- [ ] `AppShell` nav uses `<Link>`; clicking it does not trigger a full
      page reload (verify in the network tab — no document request)
- [ ] The guard's cosmetic-only nature is commented at its definition

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

- [ ] The suite runs green against the running stack from a single
      documented command
- [ ] The refresh-concurrency test fails if the `sessionGeneration` guard
      in `api.ts` is removed — verify by actually removing it, confirming
      red, and restoring. Per `backend/CLAUDE.md`'s rule, a test never
      observed to fail is not verified, only written; that applies here
      too
- [ ] The `AUTH-7` test fails if the login page is changed to
      distinguish wrong-password from unknown-email
- [ ] No test depends on a hand-maintained database row

---

**Group 1 complete — Auth end-to-end.** Backend (`T-AUTH-1` through
`T-AUTH-3`) and frontend (`T-AUTH-4`, `T-AUTH-5`) both built, reviewed,
and integrated.

**Checkpoint decisions, both resolved**: build the route guard
(`T-DEBT-2`) and stand up Playwright (`T-DEBT-3`) before `T-SR-0` opens
Group 2. Run them in that order — the guard first, so Playwright's first
tests cover the finished auth surface rather than one that's about to
change underneath them.

What the slice validated, worth noting before repeating the pattern three
more times: building vertically surfaced problems a backend-then-frontend
split would have hidden until much later — `XC-12`'s error-path CORS gap,
the refresh-concurrency bug, the `422`-vs-`409` error routing split. None
of those are visible until both halves exist and talk to each other.

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
- [ ] `T-DEBT-1`: `SubmitRequestPage` imports the shared `Field.tsx` and
      its local copy is deleted — no `Field` definition survives outside
      `components/ui/Field.tsx`
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
