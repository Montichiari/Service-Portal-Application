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
`app/main.py` — never per-route `try/except` reconstructing this shape by
hand. If a new error case needs a new `code`, add it to the `code` enum
documented in `design.md §1`'s error table and update that table in the
same change; don't invent an undocumented code inline in a route.

### Auth dependencies

`get_current_user` and `require_role(role)` live in `app/api/deps.py`,
built once in `T-AUTH-2`, and every protected route imports them from
there — never re-implements cookie-reading or role-checking inline. A
route that needs "any authenticated user" depends on `get_current_user`;
a route that needs a specific role depends on `require_role("admin")`,
which itself depends on `get_current_user` (compose, don't duplicate the
check).

### Cookies and JWT

Cookie-setting and JWT encode/decode helpers live in `app/core/security.py`
(or equivalent — pick one module and keep it there, don't scatter
`jwt.encode` calls across route files). Lifetimes (1 hr access / 30 day
refresh) and cookie attributes (`httpOnly`, `Secure`, `SameSite=Lax`) are
constants defined once in that module, referenced everywhere — changing a
lifetime should be a one-line diff, not a grep-and-replace across routes.

Refresh tokens are never stored or logged raw — only `token_hash` (matching
the existing `refresh_tokens.token_hash` column). If you find yourself
about to log a raw token "just for debugging," don't; log the `id` or
`jti` instead.

### CSRF header check

The `X-Requested-With` check (`requirements.md XC-9`) is FastAPI middleware
registered in `app/main.py`, applied globally to non-`GET` requests — not a
per-route dependency. It runs _before_ auth checks (a request failing CSRF
never needs its cookie inspected).

## Testing

Contract tests (R10, ORM phase) run against a real Postgres test database —
never SQLite. SQLite silently accepts values a `CHECK` constraint should
reject and has no native `JSONB`, so a green SQLite test can pass while the
real schema is broken. If you catch yourself reaching for an in-memory
SQLite engine "to keep tests fast," that's the wrong trade for this
project — correctness against the actual constraint set matters more here
than test runtime. This applies to API-phase tests too — an endpoint test
against SQLite proves less than it looks like it proves.

Every test lives in a transaction rolled back at teardown
(`backend/tests/db/conftest.py`'s fixture), never manual row deletion.
When adding a new constraint-enforcement test, verify it can actually
fail: temporarily comment out the constraint, confirm the test goes red,
then restore it. A constraint test that has never been observed to fail
is not verified, only written.

**API-phase additions**:

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
