"""ServiceRequest model — maps the ``service_requests`` table (design.md DDL, requirement R4)."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin


class ServiceRequest(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "service_requests"

    # `priority` is a VARCHAR + CheckConstraint, never a native Postgres ENUM
    # (locked decision — backend/CLAUDE.md, R4; same pattern as User.role in
    # Task 2). The explicit name feeds the shared naming convention's
    # %(constraint_name)s token and renders as
    # ``ck_service_requests_priority_valid``.
    __table_args__ = (
        CheckConstraint(
            "priority IN ('low', 'medium', 'high')", name="priority_valid"
        ),
    )

    requestor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # RESTRICT: a user who filed requests can't be deleted out from under
        # them (design.md "ON DELETE behavior", R8).
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        # SET NULL: an assignee leaving shouldn't block deletion; the request
        # just loses the reference (design.md "ON DELETE behavior", R8).
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    request_type: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default=text("'general'")
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'medium'")
    )
    current_status_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # RESTRICT: statuses are seed data and must not be deleted while a
        # request references them (design.md "ON DELETE behavior", R8).
        ForeignKey("statuses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        # Deliberately no server_default and no Python-side default: per
        # design.md's resolved decision #3, the application layer sets this to
        # the "open" status's id on insert. That code is a later backend task,
        # not this one; the column being briefly unset at the model layer is
        # expected at this stage.
    )
    # Column and attribute are both ``request_metadata`` (design.md DDL, R4) —
    # the name was picked up front to sidestep ``metadata``, which is reserved
    # on SQLAlchemy's DeclarativeBase. JSONB, NOT NULL, server-defaulted to an
    # empty object.
    request_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'"),
    )

    # --- Relationships -----------------------------------------------------
    # service_requests has two FKs into users.id (requestor_id, assignee_id),
    # so SQLAlchemy cannot infer which FK each relationship uses — both must
    # pass an explicit foreign_keys= (R2/R4, backend/CLAUDE.md). A missing or
    # wrong foreign_keys= here fails at mapper-configuration time, not import
    # time, so it is verified by actually instantiating the model, not by
    # reading this. back_populates targets the attributes added to User in
    # Task 2.
    requestor: Mapped["User"] = relationship(
        "User",
        back_populates="requested_service_requests",
        foreign_keys=[requestor_id],
    )
    assignee: Mapped["User | None"] = relationship(
        "User",
        back_populates="assigned_service_requests",
        foreign_keys=[assignee_id],
    )

    # Only one FK from service_requests to statuses, so no disambiguation
    # needed. Status (Task 2) declares no back reference, so this side is
    # one-directional.
    current_status: Mapped["Status"] = relationship("Status")

    # StatusHistory and Comment don't exist until Task 4 — string references
    # keep this file free of cross-model imports; the targets resolve once
    # those models register on Base.metadata. Until then configure_mappers()
    # legitimately fails on these names, same as after Task 2. Both child
    # tables' service_request_id FK is ON DELETE CASCADE (R8), so
    # passive_deletes=True lets the database cascade instead of SQLAlchemy
    # pre-emitting its own DELETEs.
    status_history: Mapped[list["StatusHistory"]] = relationship(
        "StatusHistory",
        back_populates="service_request",
        passive_deletes=True,
    )
    comments: Mapped[list["Comment"]] = relationship(
        "Comment",
        back_populates="service_request",
        passive_deletes=True,
    )
