# Backend Schema — Design (reconciled with final ERD)

> Reconciled against the final ERD, including the switch to UUID primary
> keys, the `refresh_tokens` table, and the `request_type`/`request_metadata`
> columns on `service_requests`.

## Resolved decisions (confirmed against the drawio ERD)

1. `comment.author_id` — the `(int)` label in the drawio ERD was a labeling
   slip, not an intentional design. Confirmed `UUID`, matching every other
   FK to `users.id`.
2. `status_history.status_id` — same: the `(varchar)` label was a slip.
   Confirmed `UUID`, matching `statuses.id`.
3. `service_requests.current_status_id` has no DB-level `DEFAULT`.
   Confirmed: the application sets it explicitly to the "open" status's id
   on insert, rather than seeding `statuses` with fixed literal UUIDs to
   support a hardcoded `DEFAULT`.

## DDL

```sql
-- Postgres 13+ ships gen_random_uuid() in core — no extension needed.

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    first_name      VARCHAR(100) NOT NULL,
    last_name       VARCHAR(100) NOT NULL,
    role            VARCHAR(20)  NOT NULL DEFAULT 'user'
                    CHECK (role IN ('user', 'admin')),
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE refresh_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  VARCHAR(255) NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON refresh_tokens (user_id);

CREATE TABLE statuses (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(50) NOT NULL UNIQUE,
    sort_order  INT NOT NULL,
    is_terminal BOOLEAN NOT NULL DEFAULT FALSE
);
-- seed: open(sort 1, terminal=f), in_progress(2,f), resolved(3,t), closed(4,t)

CREATE TABLE service_requests (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requestor_id       UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    assignee_id        UUID REFERENCES users(id) ON DELETE SET NULL,
    request_type       VARCHAR(50) NOT NULL DEFAULT 'general',
    title              VARCHAR(200) NOT NULL,
    description        TEXT NOT NULL,
    priority           VARCHAR(10) NOT NULL DEFAULT 'medium'
                       CHECK (priority IN ('low', 'medium', 'high')),
    current_status_id  UUID NOT NULL REFERENCES statuses(id) ON DELETE RESTRICT,
    request_metadata   JSONB NOT NULL DEFAULT '{}',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON service_requests (requestor_id);
CREATE INDEX ON service_requests (assignee_id);
CREATE INDEX ON service_requests (current_status_id);

CREATE TABLE status_history (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_request_id  UUID NOT NULL REFERENCES service_requests(id) ON DELETE CASCADE,
    status_id           UUID NOT NULL REFERENCES statuses(id) ON DELETE RESTRICT,
    changed_by_id        UUID REFERENCES users(id) ON DELETE SET NULL,
    note                TEXT,
    changed_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON status_history (service_request_id);

CREATE TABLE comments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_request_id  UUID NOT NULL REFERENCES service_requests(id) ON DELETE CASCADE,
    author_id           UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    body                TEXT NOT NULL,
    is_internal         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON comments (service_request_id);
```

## ORM foundation (locked — implement verbatim, do not re-derive)

`app/db/base.py`:

```python
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
```

`app/db/mixins.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPkMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    # DateTime(timezone=True) must be explicit — Mapped[datetime] alone
    # resolves to Postgres TIMESTAMP WITHOUT TIME ZONE by default, not the
    # TIMESTAMPTZ this schema specifies everywhere.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
```

**Any plain (non-mixin) timestamp column** — `status_history.changed_at`,
`refresh_tokens.created_at` — must use the same explicit
`DateTime(timezone=True)`, for the same reason. This isn't optional
styling; every timestamp column in this schema is `TIMESTAMPTZ` in the
DDL, with no exceptions.

**Mixin applicability — do not apply `TimestampMixin` blindly to every model:**

- `users`, `service_requests`, `comments` → use `TimestampMixin` (both columns present).
- `refresh_tokens` → `UUIDPkMixin` only; add a plain `created_at` column directly (no `updated_at` — a token is issued and later revoked/expired, never edited).
- `status_history` → `UUIDPkMixin` only; add a plain `changed_at` column directly (single timestamp, different name — a history row is immutable, so "created" and "changed" are the same event).
- `statuses` → `UUIDPkMixin` only; no timestamp columns at all (static seed data).

All models use SQLAlchemy 2.0 typed declarative style (`Mapped[...]` / `mapped_column`), not the legacy `Column(...)` style.

## ON DELETE behavior (carried forward from the original design session; not encoded in the ERD diagram itself)

- `requestor_id`, `author_id` → `RESTRICT` — a user who created records can't
  be deleted out from under them.
- `assignee_id`, `changed_by_id` → `SET NULL` — an assignee/actor leaving
  shouldn't block deletion; the record just loses that reference.
- `service_request_id` on `status_history`/`comments` → `CASCADE` — child
  audit/comment rows have no meaning without their parent request.
- `current_status_id`, `status_id` → `RESTRICT` — a status row can't be
  deleted while requests or history reference it (in practice, statuses are
  seed data and shouldn't be deleted at all).
