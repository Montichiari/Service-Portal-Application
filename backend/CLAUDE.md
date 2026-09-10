# backend/CLAUDE.md

Read `specs/backend-phase/design.md`, `requirements.md`, and `tasks.md`
before writing any ORM-phase code, and `specs/api-phase/design.md`,
`requirements.md`, and `tasks.md` before writing any API-phase code. This
file holds conventions that apply across every task and every `/clear`
reset — don't re-derive them.

## ORM style

SQLAlchemy 2.0 typed declarative style only: `Mapped[...]` /
`mapped_column(...)`. Never the legacy `Column(...)` style, even in code
you're only skimming for reference elsewhere in the repo.

Every model imports `Base` from `app/db/base.py` and the relevant mixin(s)
from `app/db/mixins.py`. Never redefine `Base`, the naming convention, or
a mixin inline in a model file — if a mixin doesn't fit a table, that's a
signal to add a plain column on that one model, not to modify the shared
mixin (see `design.md`'s mixin applicability table).

## Model file structure

One model per file under `app/db/models/`, filename matching the table
name singular (`user.py` → `User`, `service_request.py` →
`ServiceRequest`). Import models from other files by string reference in
`relationship(...)` calls (`relationship("ServiceRequest", ...)`), never
by direct Python import across model files — avoids circular imports
given how interconnected this schema is.

`app/db/models/__init__.py` re-exports every model
(`from app.db.models.user import User`, etc., one line per model). Any
code that needs "every model registered on `Base.metadata`" — most
notably `alembic/env.py` — imports from this `__init__.py`, not from
each model module individually. When a new model is added, updating
`__init__.py` is part of that task, not a separate follow-up — a model
missing from `__init__.py` won't register on `Base.metadata` and won't
show up in autogenerate diffs, silently.

## Constraints

Enum-like columns (`role`, `priority`, `request_type` if it ever gets
constrained) are `VARCHAR` + `CheckConstraint` in `__table_args__`, never
a native Postgres `ENUM` type. This is a locked decision, not a default —
don't "improve" it to an `ENUM` even if it looks cleaner; `ENUM` alter is
a genuine operational cost that varchar + check avoids.

## Foreign keys

Every FK's `ondelete=` must match `design.md`'s ON DELETE table exactly.
When a `relationship()`'s FK uses `CASCADE`, pair it with
`passive_deletes=True`.

When two FKs on the same table point at the same target table (e.g.
`service_requests.requestor_id` and `assignee_id`, both → `users.id`),
every `relationship()` on both sides must pass an explicit
`foreign_keys=` argument. SQLAlchemy cannot infer which FK a relationship
means once there's more than one candidate — this fails at mapper
configuration time, not at import time, so it can pass a casual read and
still be broken. Confirm by actually instantiating the model, not by
inspection alone.

## Migrations

`alembic revision --autogenerate` only after all models for a given task
group are written — read `tasks.md` for which task groups are meant to
produce one migration together vs. separately.

Never run `alembic upgrade head` as part of generating a migration. The
generated file is a review checkpoint: present it and stop. Applying it is
a separate, explicit step the person takes after reviewing.

No new migration is expected anywhere in the API phase — every model the
API layer needs already exists from the ORM phase (the one candidate
addition, a `ticket_number` column, was decided against — see
`specs/api-phase/design.md §0`). If a task seems to need a schema change,
stop and flag it rather than assuming one is in scope.

## API-phase conventions

The sections below apply to `specs/api-phase/tasks.md` work. The ORM-phase
sections above still apply wherever they're relevant (model conventions
don't change because a new phase started) — these are additions, not
replacements.

### Route organization

One router per resource under `app/api/routes/`, mirroring the "one model
per file" rule above: `auth.py`, `statuses.py`, `service_requests.py`,
`comments.py`, `status_changes.py`. Each router is mounted in
`app/main.py` with its `/api/v1` prefix — never hardcode the prefix inside
an individual route path.

Pydantic request/response schemas live in `app/api/schemas/`, one file per
resource, matching the router split — not inline in the route files, and
not reusing SQLAlchemy models directly as response models (a `User` ORM
model has `password_hash`; a response schema must not).

### Error envelope

The envelope shape is fixed by `specs/api-phase/design.md §1` and
`requirements.md XC-4`:

```json
{ "error": { "code": "...", "message": "...", "fields": {...} } }
```

Implemented via FastAPI exception handlers registered once in
`app/main.py`'s `create_app()` — never per-route `try/except`
reconstructing this shape by hand. If a new error case needs a new
`code`, add it to the `code` enum documented in `design.md §1`'s error
table and update that table in the same change; don't invent an
undocumented code inline in a route.

**Three handlers are required, not one**: `RequestValidationError` (→
`422`, `XC-4`), framework-raised `HTTPException` including an unmatched
route (→ envelope-wrapped, still `XC-4`), and a true catch-all for any
other unhandled exception (→ `500`/`INTERNAL_ERROR`, `XC-14`). The third
is the easiest to forget because nothing exercises it in normal
development — routes don't throw arbitrary exceptions on purpose — but
it's the one that matters most for never leaking a stack trace or an
internal error message to a client. The catch-all must still log the full
traceback server-side: suppressed for the client, not suppressed for the
operator.

**The trap worth knowing about** (`XC-15`, found reviewing `T-AUTH-2`):
`response_model` filtering and error handling are the same security
boundary, and only one of them looks like it. If serialization against a
`response_model` fails, FastAPI's `ResponseValidationError` carries the
offending value in its own message — and that value is precisely the
field `response_model` existed to exclude (a `User` row's
`password_hash`, say). A `500` handler doing `str(exc)` turns a careful
exclusion into a live leak, via a path no success-path test ever touches.
Never render an exception's own text into a response body. When you write
an exception-origin test, cover all four origins — route body,
dependency, response serialization, middleware stack — not just the
obvious one.

### App construction

`app/main.py` exposes a `create_app()` factory (built in `T-AUTH-2`) —
tests construct the app through this factory too, so a test run exercises
the actual app the server runs, not a hand-assembled lookalike that could
silently drift from it (missing a middleware registration, wrong handler
order). Never construct a second `FastAPI()` instance elsewhere "for
tests" or "for a script."

### Auth dependencies

`get_current_user` and `require_role(role)` live in `app/api/deps.py`,
built once in `T-AUTH-2`, and every protected route imports them from
there — never re-implements cookie-reading or role-checking inline. A
route that needs "any authenticated user" depends on `get_current_user`;
a route that needs a specific role depends on `require_role("admin")`,
which itself depends on `get_current_user` (compose, don't duplicate the
check). `require_role` is rank-based against the two-role hierarchy
(`user` < `admin`), not exact-match — an admin passes a
`require_role("user")` gate, matching `XC-6`'s "minimum required role"
wording.

**`get_current_user`'s source of truth**: loads the full user row from the
database on every protected request rather than trusting the JWT's `role`
claim alone (`requirements.md XC-13`) — decided during `T-AUTH-2`,
reversing `design.md`'s original zero-DB-hit rationale on purpose. The
token's signature/expiry check still happens first as a cheap pre-filter;
the DB row is the final word on `role` and on whether the user is still
active or exists at all.

### Cookies and JWT

Cookie-setting and JWT encode/decode helpers live in `app/core/security.py`
(built in `T-AUTH-1` — pick one module and keep it there, don't scatter
`jwt.encode` calls across route files). Lifetimes (1 hr access / 30 day
refresh) and cookie attributes (`httpOnly`, `Secure`, `SameSite=Lax`) are
constants defined once in that module, referenced everywhere — changing a
lifetime should be a one-line diff, not a grep-and-replace across routes.
`clear_auth_cookies` lives alongside the setters, same module — logout
needs matching attributes to actually clear a cookie, and that's the same
concern as setting one.

**Boundary with `app/config.py`**: genuinely environment-specific values
(`JWT_SECRET_KEY`, `JWT_ALGORITHM`) stay in `config.py`/`.env`. Everything
that's a project-wide constant regardless of environment (lifetimes,
cookie attributes, `MAX_PASSWORD_BYTES`) lives in `security.py` instead —
`config.py` is for "differs per environment," not "differs per developer's
preference for where to put a number."

Password hashing uses `bcrypt` directly, not `passlib[bcrypt]` — passlib
1.7.4 is unmaintained and its backend probe breaks against bcrypt ≥4.1
(raises `ValueError` on every hash call). Found and documented in
`security.py`'s docstring during `T-AUTH-1` — don't reintroduce passlib
later without knowing this.

`security.py` exports `MAX_PASSWORD_BYTES = 72` (bcrypt's hard limit).
`hash_password` raises rather than silently truncating an over-long
password — truncation would make every password sharing a 72-byte prefix
interchangeable, which is worse than rejecting it. Any register-schema
validation against this limit imports the constant; it is never
re-hardcoded as a literal `72` a second place.

**Known gap, not blocking dev/demo work**: `.env`/`.env.example` currently
ship the placeholder `JWT_SECRET_KEY=change-me-to-a-long-random-secret`.
Fine for local development; every token is signed with a value that's
committed to the repo, so this must be rotated to a real secret before any
real deployment.

Refresh tokens are never stored or logged raw — only `token_hash` (matching
the existing `refresh_tokens.token_hash` column). If you find yourself
about to log a raw token "just for debugging," don't; log the `id` or
`jti` instead.

### CSRF header check

The `X-Requested-With` check (`requirements.md XC-9`) is FastAPI middleware
registered in `app/main.py` via `create_app()`, applied to every
state-changing request — not a per-route dependency. It checks header
_presence_, any value, not an exact string — pinning to `XMLHttpRequest`
specifically would only break compatible clients for no security benefit.
`GET`, `HEAD`, and `OPTIONS` are exempt (`OPTIONS` because it's the
browser's CORS preflight, which can't carry a custom header). It runs
_before_ auth checks — a request failing CSRF never needs its cookie
inspected.

### CORS

`FRONTEND_ORIGIN` (from `app/config.py` — environment-specific, same
boundary as `JWT_SECRET_KEY`) is the sole allowed origin in FastAPI's
`CORSMiddleware`, with `allow_credentials=True`. Never widen this to a
wildcard `*` — CORS itself forbids combining a wildcard origin with
credentials, so it isn't even a valid shortcut, just a broken one. Wired
in `T-AUTH-3` (`XC-12`), not `T-AUTH-2` — it's backend-only but has no
consumer until the frontend client exists.

**Verify this covers error responses too**, not just `2xx` — a common
`CORSMiddleware` ordering mistake exempts error responses from getting
CORS headers, in which case the browser reports a `401`/`403`/`422`/`500`
to `fetch` as an opaque network failure instead of a readable response.
Test a failing cross-origin request explicitly; don't infer it from a
passing success-path test.

**The `500` path is a documented exception** (`T-AUTH-3`): Starlette hangs
the `Exception` catch-all off `ServerErrorMiddleware`, the outermost
layer, so that response never passes back through `CORSMiddleware`. The
handler therefore attaches CORS headers itself via `app/api/cors.py`,
using the same origin allow-list. **Don't "fix" this by moving the
exception handler inward** — it would gain CORS automatically but lose
`XC-14`'s tested guarantee that exceptions raised inside the middleware
stack are still caught. The current arrangement is the resolution of a
real tension between two requirements, not an oversight.

### Email handling

Email addresses are case-folded to lowercase through a single shared
`normalize_email` function, applied on both storage and lookup
(`AUTH-17`). Never fold at one and not the other, and never inline the
`.lower()` call at a call site — Postgres' unique index compares exactly,
so a single unfolded path silently creates duplicate accounts that differ
only in case.

`requirements.txt` includes `email-validator` (Pydantic's `EmailStr`
requires it as an optional extra). Note that it rejects `.test` as a
reserved TLD, so API tests use `@example.com` addresses rather than the
DB fixtures' `@example.test`.

## Testing

Contract tests (R10, ORM phase) run against a real Postgres test database —
never SQLite. SQLite silently accepts values a `CHECK` constraint should
reject and has no native `JSONB`, so a green SQLite test can pass while the
real schema is broken. If you catch yourself reaching for an in-memory
SQLite engine "to keep tests fast," that's the wrong trade for this
project — correctness against the actual constraint set matters more here
than test runtime. This applies to API-phase tests too — an endpoint test
against SQLite proves less than it looks like it proves.

Every test lives in a transaction rolled back at teardown (the
`db_session` fixture — originally `backend/tests/db/conftest.py`, scoped
to that package only), never manual row deletion. When adding a new
constraint-enforcement test, verify it can actually fail: temporarily
comment out the constraint, confirm the test goes red, then restore it. A
constraint test that has never been observed to fail is not verified,
only written.

**API-phase additions**:

- `db_session` was promoted to a top-level `backend/tests/conftest.py`
  during `T-AUTH-2` (needed early for that task's own tests, not deferred
  to `T-AUTH-3` as originally planned). `_prepared_database` was made
  non-autouse in the same change specifically so `tests/core/` still runs
  with no Postgres available — verified against an unreachable DB URL.
  Keep that property: a change here that makes Postgres implicitly
  required for `tests/core/` again is a regression, not a simplification.
- Any test client used for cookie-based auth flows must use
  `base_url="https://testserver"`, never an `http://` base — the auth
  cookies are `Secure`, and `httpx` silently drops `Secure` cookies
  against a non-`https` base URL. This fails in a way that looks exactly
  like a broken auth flow, not a test-config problem, so get it right
  from the start rather than debugging it as a mystery.
- Auth-flow tests need a test client that persists cookies across calls
  within one test (register → login → authenticated call, as one
  sequence) — set this up once as a fixture in
  `backend/tests/api/conftest.py`, don't hand-roll cookie jars per test.
- When a test asserts an error response, assert against the full envelope
  shape (`error.code`, `error.message` presence, `error.fields` keys where
  applicable) — not just the HTTP status code. A `422` with the wrong
  `fields` key is still a contract violation even though the status code
  is right.
- `SC-5`/`SC-6`'s atomicity requirement needs the same "verify it can
  fail" discipline as a constraint test — force the transaction to fail
  partway and assert _neither_ write landed, not just that the endpoint
  returned an error.
- `requirements.txt` includes `httpx2`, not `httpx` — this Starlette
  version's `TestClient` requires that specific package. Don't "correct"
  it back to `httpx` if you see it and don't recognize the name.
- **Never derive a test's expected value from the constant under test.**
  Found in `T-AUTH-3`: the cookie-expiry assertion computed its expectation
  from `ACCESS_TOKEN_TTL`, so changing that constant to 30 days left the
  test green — it asserted self-consistency, not correctness. Pin
  expectations to the literal values the requirement states
  (`3600`/`2592000` from `AUTH-6`), with a comment explaining why the
  constant deliberately isn't imported. Same failure family as a tamper
  test that passes for the wrong reason.

## Task workflow

One task from `tasks.md` per session (ORM phase or API phase, whichever is
current). Implement, verify against that task's acceptance criteria
checklist, stop — do not start the next task in the same session. `/clear`
before starting the next task.

## Non-goals — ORM phase (historical, complete)

- No API routes, no FastAPI path operations
- No Pydantic request/response schemas
- No auth logic (password hashing, JWT issuance/validation) — models only
- No seed data beyond the four `statuses` rows specified in `requirements.md`
- No application-level logic for setting `current_status_id` on insert

All of the above are now in scope — see Non-goals below for what's still
out of scope in the current phase.

## Non-goals — API phase (current)

- No rate limiting on `/auth/login` — explicitly deferred
  (`specs/api-phase/design.md §7`)
- No email verification at registration
- No `PATCH /service-requests/{id}` — no frontend surface needs it yet
  (`specs/api-phase/design.md §7`)
- No `request_type` values beyond `'general'`
- No admin-promotion endpoint — role changes remain a direct DB operation
