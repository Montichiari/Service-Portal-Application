# Backend — ORM Layer Requirements

Scope: SQLAlchemy models + Alembic migration for the six tables in
`design.md`. Does not cover API routes, Pydantic schemas, or auth logic —
those are later backend tasks, out of scope here.

All models live under `app/db/models/`, one file per entity
(`user.py`, `status.py`, `service_request.py`, `status_history.py`,
`comment.py`, `refresh_token.py`), importing `Base` and the mixins from
`app/db/base.py` / `app/db/mixins.py` exactly as specified in `design.md` —
do not redefine or modify those two files.

---

## R1 — ORM foundation

- THE SYSTEM SHALL implement `app/db/base.py` and `app/db/mixins.py`
  exactly as given in `design.md`'s "ORM foundation" section, verbatim,
  with no modification to the naming convention or mixin field names.
- THE SYSTEM SHALL apply `TimestampMixin` only to `User`, `ServiceRequest`,
  and `Comment`, per the mixin applicability table in `design.md`.
- THE SYSTEM SHALL NOT apply `TimestampMixin` to `RefreshToken`,
  `StatusHistory`, or `Status` — see `design.md` for each one's actual
  timestamp columns, if any.
- THE SYSTEM SHALL declare every timestamp column — whether via
  `TimestampMixin` or a plain column on `RefreshToken`/`StatusHistory` —
  with `DateTime(timezone=True)` explicit in `mapped_column(...)`.
  `Mapped[datetime]` alone resolves to Postgres `TIMESTAMP WITHOUT TIME
ZONE`, not the `TIMESTAMPTZ` every timestamp column in `design.md`'s DDL
  specifies.

## R2 — User

- THE SYSTEM SHALL define a `User` model mapped to `users`, with columns
  and types exactly matching `design.md`'s DDL for that table.
- THE SYSTEM SHALL enforce the `role` CHECK constraint (`'user'`, `'admin'`)
  via SQLAlchemy `CheckConstraint` in `__table_args__`, not a native
  Postgres ENUM type.
- THE SYSTEM SHALL define `relationship()` attributes for every table that
  references `users.id`: `refresh_tokens`, `requested_service_requests`
  (via `requestor_id`), `assigned_service_requests` (via `assignee_id`),
  `comments`, `status_changes` (via `status_history.changed_by_id`).
- WHEN a `service_requests` row has two FKs to the same `users.id` column
  (`requestor_id`, `assignee_id`), THE SYSTEM SHALL disambiguate both
  corresponding `relationship()` calls with an explicit `foreign_keys=`
  argument — SQLAlchemy cannot infer which FK a relationship refers to
  when more than one exists between the same two tables.

## R3 — Status

- THE SYSTEM SHALL define a `Status` model mapped to `statuses`, with
  `name` unique and `sort_order`/`is_terminal` as plain non-nullable
  columns per `design.md`.
- THE SYSTEM SHALL NOT add a Python-level or DB-level `CheckConstraint`
  restricting `name` to a fixed set of values — status names are seed data
  managed by migration, not an enum.
- THE SYSTEM SHALL include a data migration (in the same Alembic revision
  or a follow-up one — Claude Code's choice, state which) that seeds the
  four rows: `open` (sort 1, not terminal), `in_progress` (sort 2, not
  terminal), `resolved` (sort 3, terminal), `closed` (sort 4, terminal).

## R4 — ServiceRequest

- THE SYSTEM SHALL define a `ServiceRequest` model mapped to
  `service_requests`, with columns and types exactly matching `design.md`.
- THE SYSTEM SHALL enforce the `priority` CHECK constraint (`'low'`,
  `'medium'`, `'high'`) via `CheckConstraint`, matching R2's approach for
  `role`.
- THE SYSTEM SHALL leave `current_status_id` NOT NULL with no DB-level
  `DEFAULT` — per `design.md`'s resolved decision, the application layer (a later
  backend task, not this one) is responsible for setting it to the "open"
  status's id on insert. Do not invent a hardcoded default here.
- THE SYSTEM SHALL type `request_metadata` as `JSONB` with a non-nullable
  default of an empty object (`{}`). Both the database column and the
  Python attribute are named `request_metadata` — the name was chosen at
  the column level, not just the ORM level, specifically to avoid
  colliding with `DeclarativeBase`'s reserved `metadata` class attribute.
  There is no separate override mapping; `mapped_column(JSONB, ...)`
  needs no explicit column-name argument.
- THE SYSTEM SHALL define `relationship()` attributes back to `requestor`
  and `assignee` (both on `User`, both requiring `foreign_keys=` per R2),
  and forward to `status_history` and `comments` collections.

## R5 — StatusHistory

- THE SYSTEM SHALL define a `StatusHistory` model mapped to
  `status_history`, with `changed_at` as its only timestamp column
  (server-default `now()`, no `updated_at` — see R1), declared with
  `DateTime(timezone=True)` explicit per R1's requirement.
- THE SYSTEM SHALL define `service_request_id` and `status_id` as NOT
  NULL FKs, and `changed_by_id` as a nullable FK — this nullability is
  intentional (see design discussion in chat: a status change may be
  system-initiated or its actor's account may later be deleted) and SHALL
  NOT be changed to NOT NULL without confirming with the person first.

## R6 — Comment

- THE SYSTEM SHALL define a `Comment` model mapped to `comments`, with
  `TimestampMixin` applied (both `created_at` and `updated_at` — comments
  are editable, unlike `status_history` rows).
- THE SYSTEM SHALL default `is_internal` to `false`.

## R7 — RefreshToken

- THE SYSTEM SHALL define a `RefreshToken` model mapped to
  `refresh_tokens`, with a plain `created_at` column only (no
  `updated_at` — see R1) and nullable `revoked_at`, both declared with
  `DateTime(timezone=True)` explicit per R1's requirement.
- THE SYSTEM SHALL index `token_hash` (`mapped_column(..., index=True)`)
  — token validation looks tokens up by `token_hash`, and this access
  pattern needs an index even though `design.md`'s original ERD-derived
  DDL didn't call for one.

## R8 — Cascade / delete behavior

- THE SYSTEM SHALL set every FK's `ondelete` argument to match the table
  in `design.md`'s "ON DELETE behavior" section exactly: `RESTRICT` for
  `requestor_id`/`author_id`, `SET NULL` for `assignee_id`/`changed_by_id`,
  `CASCADE` for `service_request_id` on `status_history`/`comments`,
  `RESTRICT` for `current_status_id`/`status_id`, `CASCADE` for
  `refresh_tokens.user_id`.
- THE SYSTEM SHALL pass `passive_deletes=True` specifically on the
  **parent-side collection relationship** for every FK that uses
  `CASCADE` — `ServiceRequest.status_history`, `ServiceRequest.comments`,
  `User.refresh_tokens` — not on the child's many-to-one relationship
  back to its parent (`StatusHistory.service_request`,
  `Comment.service_request`, `RefreshToken.user`). `passive_deletes=True`
  only changes behavior on the side representing the collection that
  would otherwise be eagerly loaded when the parent is deleted; setting
  it on the child's back-reference has no meaningful effect. It is
  harmless to also set it on the child side, but doing so there ALONE
  does not satisfy this requirement.

## R9 — Migration

- THE SYSTEM SHALL run `alembic revision --autogenerate` only after every
  model in R2–R7 is written and importable — not incrementally per model —
  so the first migration is a single coherent "initial schema" revision.
- WHEN the autogenerate output is produced, THE SYSTEM SHALL NOT apply it
  automatically (`alembic upgrade head`) — this is a manual review
  checkpoint per project convention; Claude Code should present the
  generated migration file for the person to review first.

## R10 — Contract tests against the schema

Scope: verify the applied schema actually behaves the way `design.md`
specifies — not integration/end-to-end testing (that's Phase 6). Tests run
against a real Postgres test database, never SQLite — SQLite doesn't
enforce `CHECK` constraints the same way and has no `JSONB` type, so a
passing SQLite test would validate the wrong schema.

- THE SYSTEM SHALL include a test asserting that inserting a `User` with
  an out-of-range `role` value, or a `ServiceRequest` with an out-of-range
  `priority` value, raises `IntegrityError` — proves the `CheckConstraint`s
  from R2/R4 are actually enforced by the database, not just declared.
- THE SYSTEM SHALL include a test that instantiates a `ServiceRequest`
  with distinct `requestor` and `assignee` users and asserts both
  relationships resolve to the correct, distinct `User` rows — proves the
  `foreign_keys=` disambiguation from R2/R4 is correctly wired, since a
  misconfigured dual-FK relationship fails at mapper configuration time
  and can pass a casual code read.
- THE SYSTEM SHALL include cascade-behavior tests for each `ondelete` rule
  in R8: deleting a `ServiceRequest` removes its `status_history` and
  `comments` rows (`CASCADE`); deleting a `User` who is a `assignee` sets
  `assignee_id` to `NULL` on their requests rather than blocking the
  delete (`SET NULL`); deleting a `User` who is a `requestor` is blocked
  (`RESTRICT`).
- THE SYSTEM SHALL include a migration round-trip test: `alembic upgrade
head` → `alembic downgrade base` → `alembic upgrade head` all succeed
  without error.
- THE SYSTEM SHALL include a test asserting the four seeded `statuses`
  rows from R3 exist with correct `sort_order`/`is_terminal` values after
  migration.
- THE SYSTEM SHALL isolate each test in a transaction that rolls back at
  teardown, rather than manually deleting rows between tests.
