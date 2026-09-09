"""StatusHistory model — maps the ``status_history`` table (design.md DDL, requirement R5)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import UUIDPkMixin


class StatusHistory(UUIDPkMixin, Base):
    __tablename__ = "status_history"

    # UUIDPkMixin only — no TimestampMixin. A history row is immutable, so
    # "created" and "changed" are the same event: the table carries a single
    # `changed_at` column, not the created_at/updated_at pair (design.md mixin
    # applicability table, R1/R5).

    service_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # CASCADE: a child audit row has no meaning without its parent request
        # (design.md "ON DELETE behavior", R8).
        ForeignKey("service_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # RESTRICT: statuses are seed data and must not be deleted while a
        # history row references them (design.md "ON DELETE behavior", R8).
        # Type is UUID — the drawio ERD's "(varchar)" label on this field was a
        # labeling slip (design.md resolved decision #2), matching statuses.id.
        ForeignKey("statuses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        # SET NULL, and intentionally NULLABLE: a status change may be
        # system-initiated, or its actor's account may later be deleted
        # (design.md "ON DELETE behavior", R5). Do NOT "fix" this to NOT NULL.
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Plain (non-mixin) timestamp column — still declared with
    # DateTime(timezone=True) explicit, or it resolves to Postgres TIMESTAMP
    # WITHOUT TIME ZONE instead of the TIMESTAMPTZ the DDL specifies (design.md
    # R1; same correction as Task 2's TimestampMixin fix).
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # --- Relationships --------------------------------------------------------
    # back_populates targets the attribute names declared on the other side in
    # Tasks 2/3: ServiceRequest.status_history and User.status_changes. A
    # misspelled name fails at configure_mappers() time, not import time.
    service_request: Mapped["ServiceRequest"] = relationship(
        "ServiceRequest",
        back_populates="status_history",
        # service_request_id is ON DELETE CASCADE (R8) — let the DB cascade
        # rather than SQLAlchemy emitting its own DELETEs first.
        passive_deletes=True,
    )
    # Status declares no back reference (Task 2), so this side is
    # one-directional — same shape as ServiceRequest.current_status in Task 3.
    status: Mapped["Status"] = relationship("Status")
    changed_by: Mapped["User | None"] = relationship(
        "User",
        back_populates="status_changes",
        # changed_by_id is the only FK from status_history to users, but the
        # User.status_changes side pins foreign_keys= explicitly; mirror it
        # here so the pair stays unambiguous.
        foreign_keys=[changed_by_id],
    )
