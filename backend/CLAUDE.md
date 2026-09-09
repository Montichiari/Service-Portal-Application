# Backend — Claude Code conventions

Read `specs/backend-phase/design.md`, `requirements.md`, and `tasks.md`
before writing any code. This file holds conventions that apply across
every task and every `/clear` reset — don't re-derive them.

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

## Testing

Contract tests (R10) run against a real Postgres test database — never
SQLite. SQLite silently accepts values a `CHECK` constraint should reject
and has no native `JSONB`, so a green SQLite test can pass while the real
schema is broken. If you catch yourself reaching for an in-memory SQLite
engine "to keep tests fast," that's the wrong trade for this project —
correctness against the actual constraint set matters more here than
test runtime.

Every test lives in a transaction rolled back at teardown
(`backend/tests/db/conftest.py`'s fixture), never manual row deletion.
When adding a new constraint-enforcement test, verify it can actually
fail: temporarily comment out the constraint, confirm the test goes red,
then restore it. A constraint test that has never been observed to fail
is not verified, only written.

## Task workflow

One task from `tasks.md` per session. Implement, verify against that
task's acceptance criteria checklist, stop — do not start the next task in
the same session. `/clear` before starting the next task.

## Non-goals for this phase

- No API routes, no FastAPI path operations
- No Pydantic request/response schemas
- No auth logic (password hashing, JWT issuance/validation) — models only
- No seed data beyond the four `statuses` rows specified in `requirements.md`
- No application-level logic for setting `current_status_id` on insert —
  that's a later backend task; this phase only leaves the column NOT NULL
  with no DB default, per the resolved decision in `design.md`
