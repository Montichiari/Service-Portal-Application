"""User model — maps the ``users`` table (design.md DDL, requirement R2)."""

from sqlalchemy import Boolean, CheckConstraint, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin


class User(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "users"

    # `role` is a VARCHAR + CheckConstraint, never a native Postgres ENUM
    # (locked decision — see backend/CLAUDE.md and R2). The explicit name is
    # required because the shared naming convention references
    # %(constraint_name)s; it renders as ``ck_users_role_valid``.
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="role_valid"),
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'user'")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    # --- Relationships ----------------------------------------------------
    # ServiceRequest, StatusHistory, Comment and RefreshToken are added in
    # later tasks (Tasks 3-4). They are referenced by string here so this
    # file stays free of cross-model imports (backend/CLAUDE.md) and the
    # targets resolve once those models register on Base.metadata. Until
    # then, configure_mappers() legitimately fails on these names — that is
    # expected at this stage, not a defect.

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        # refresh_tokens.user_id is ON DELETE CASCADE (R8) — let the DB
        # cascade instead of SQLAlchemy emitting its own DELETEs first.
        passive_deletes=True,
    )
    requested_service_requests: Mapped[list["ServiceRequest"]] = relationship(
        "ServiceRequest",
        back_populates="requestor",
        # service_requests has two FKs to users.id — disambiguate (R2).
        foreign_keys="ServiceRequest.requestor_id",
    )
    assigned_service_requests: Mapped[list["ServiceRequest"]] = relationship(
        "ServiceRequest",
        back_populates="assignee",
        foreign_keys="ServiceRequest.assignee_id",
    )
    comments: Mapped[list["Comment"]] = relationship(
        "Comment",
        back_populates="author",
    )
    status_changes: Mapped[list["StatusHistory"]] = relationship(
        "StatusHistory",
        back_populates="changed_by",
        foreign_keys="StatusHistory.changed_by_id",
    )
