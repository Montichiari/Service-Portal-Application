# Backend — ORM Layer Tasks

Each task = one Claude Code prompt = one commit, after manual review.
`/clear` between tasks. Every task should reference `design.md` and
`requirements.md` directly rather than restating their contents in the
prompt — that's the whole point of having written them.

---

## Task 1 — Alembic init + foundation wiring

**Builds:** `app/db/base.py`, `app/db/mixins.py` (verbatim from
`design.md`), `alembic/` scaffold, `alembic/env.py` wired to
`Base.metadata` and reading the DB URL from settings/env (matching the
docker-compose Postgres service).

**Depends on:** nothing (foundation task).

**Acceptance criteria**

- [ ] `app/db/base.py` and `app/db/mixins.py` match `design.md`'s "ORM
      foundation" section exactly — no deviation in naming convention or
      mixin fields.
- [ ] `alembic/env.py` imports `Base` and sets `target_metadata =
    Base.metadata`.
- [ ] `alembic revision --autogenerate` runs without error against an
      empty database and produces an (expectedly empty, since no models
      exist yet) migration — confirms the wiring works before any entity
      is written.
- [ ] No model files exist yet — this task is foundation only.

---

## Task 2 — User + Status models

**Builds:** `app/db/models/user.py`, `app/db/models/status.py`.

**Depends on:** Task 1 (`Base`, mixins).

**Acceptance criteria**

- [ ] `User` matches R2 in `requirements.md`: columns/types from
      `design.md`, `role` CHECK constraint via `CheckConstraint` (not a
      native ENUM), `TimestampMixin` applied.
- [ ] `User` relationship attributes are declared for `refresh_tokens`,
      `requested_service_requests`, `assigned_service_requests`,
      `comments`, `status_changes` — even though the tables on the other
      side don't exist until Tasks 3–4. Use string references
      (`relationship("ServiceRequest", ...)`) so forward references
      resolve once those models exist.
- [ ] `Status` matches R3: `name` unique, no CHECK constraint on values,
      `UUIDPkMixin` only (no timestamps).
- [ ] Neither model references `ServiceRequest`, `StatusHistory`, etc. by
      direct import — string-based relationship targets only, to avoid
      circular imports.

---

## Task 3 — ServiceRequest model

**Builds:** `app/db/models/service_request.py`.

**Depends on:** Task 2 (`User`, `Status`).

**Acceptance criteria**

- [ ] Matches R4: columns/types from `design.md`, `priority` CHECK
      constraint, `request_metadata` as `JSONB` defaulting to `{}`,
      `current_status_id` NOT NULL with **no** DB-level default (per the
      resolved decision in `design.md` — do not invent one).
- [ ] `requestor` and `assignee` relationships both to `User`, each with
      an explicit `foreign_keys=` argument per R2 — confirm this actually
      resolves (import and instantiate the model in a throwaway script or
      test) rather than assuming it's correct.
- [ ] `TimestampMixin` applied.
- [ ] `ON DELETE` behavior on `requestor_id` (`RESTRICT`) and
      `assignee_id` (`SET NULL`) set via each FK's `ondelete=` argument,
      matching R8.

---

## Task 4 — StatusHistory, Comment, RefreshToken models

**Builds:** `app/db/models/status_history.py`, `app/db/models/comment.py`,
`app/db/models/refresh_token.py`.

**Depends on:** Task 3 (`ServiceRequest`).

**Acceptance criteria**

- [ ] `StatusHistory` matches R5: `changed_at` only (no `updated_at`),
      `changed_by_id` nullable and left nullable — do not "fix" this to
      NOT NULL.
- [ ] `Comment` matches R6: `TimestampMixin` applied (both columns,
      unlike `StatusHistory`), `is_internal` defaults `false`.
- [ ] `RefreshToken` matches R7: `created_at` only, `revoked_at` nullable.
- [ ] All FK `ondelete` values match R8's table exactly, including
      `CASCADE` on `service_request_id` (both tables) and
      `refresh_tokens.user_id`.
- [ ] Every `relationship()` whose FK is `CASCADE` sets
      `passive_deletes=True`, per R8.

---

## Task 5 — Migration generation (review checkpoint — do not auto-apply)

**Builds:** one Alembic revision file (`alembic revision --autogenerate
-m "initial schema"`), plus a data migration seeding the four `statuses`
rows per R3.

**Depends on:** Tasks 1–4 (every model must be written and importable
first — this is one coherent revision, not five incremental ones, per R9).

**Acceptance criteria**

- [ ] The generated migration is presented for manual review, not applied.
      Claude Code should stop after generating it and summarize what it
      contains — do not run `alembic upgrade head` in this task.
- [ ] The person reviews the migration file line by line against
      `design.md` before it's applied (this is the same discipline as
      reviewing a frontend task's diff before commit).
- [ ] Once reviewed and applied, the actual Postgres schema
      (`\d+ <table>` in `psql`) is spot-checked against `design.md` for at
      least the tables with the trickiest constraints: `service_requests`
      (CHECK + JSONB default) and `status_history` (nullable FK).
- [ ] The same `psql \d+` spot-check confirms every timestamp column
      across all six tables renders as `timestamp with time zone`, not
      `timestamp without time zone` — this was found to silently default
      wrong once already (see Task 2 correction) and is easy to miss
      without directly inspecting the applied column type.

---

## Task 6 — Contract tests against the schema

**Builds:** `backend/tests/db/conftest.py` (transaction-rollback
fixture), one test file per model under `backend/tests/db/` mirroring
`app/db/models/`.

**Depends on:** Task 5 (needs the applied migration to run tests against).

**Acceptance criteria**

- [ ] Tests run against a real Postgres test database (a `test` database
      on the existing docker-compose Postgres service, or a dedicated
      compose service), never SQLite, per R10.
- [ ] Every CHECK constraint test (`role`, `priority`) actually triggers
      `IntegrityError` when run — confirm by temporarily breaking the
      constraint and watching the test fail, then restoring it. A
      passing constraint test that was never seen to fail is not
      trustworthy.
- [ ] The dual-FK disambiguation test (`ServiceRequest.requestor` vs.
      `.assignee`) asserts on the actual resolved `User.id` values, not
      just that the attribute is non-`None`.
- [ ] All three `ON DELETE` behaviors from R8 have a passing test:
      `CASCADE`, `SET NULL`, `RESTRICT`.
- [ ] Migration round-trip test passes: `upgrade head` → `downgrade base`
      → `upgrade head`.
- [ ] Seed data test confirms all four `statuses` rows and their
      `sort_order`/`is_terminal` values.
- [ ] `conftest.py`'s fixture wraps each test in a transaction rolled
      back at teardown — no test manually deletes rows to clean up after
      itself.
