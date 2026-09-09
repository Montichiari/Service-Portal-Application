"""RefreshToken model — maps the ``refresh_tokens`` table (design.md DDL, requirement R7)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import UUIDPkMixin


class RefreshToken(UUIDPkMixin, Base):
    __tablename__ = "refresh_tokens"

    # UUIDPkMixin only — no TimestampMixin. A token is issued and later
    # revoked/expired, never edited, so it has created_at but no updated_at
    # (design.md mixin applicability table, R1/R7).

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # CASCADE: tokens are worthless once their user is gone (design.md
        # "ON DELETE behavior", R8).
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Indexed (R7): token validation looks refresh tokens up by token_hash.
    # design.md's ERD-derived DDL didn't call for this index.
    token_hash: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Plain (non-mixin) timestamp column — DateTime(timezone=True) explicit for
    # the same reason as StatusHistory.changed_at: bare Mapped[datetime]
    # resolves to TIMESTAMP WITHOUT TIME ZONE, not the TIMESTAMPTZ the DDL
    # specifies (design.md R1; Task 2 correction).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # --- Relationships --------------------------------------------------------
    # back_populates targets User.refresh_tokens, declared in Task 2.
    user: Mapped["User"] = relationship(
        "User",
        back_populates="refresh_tokens",
        # user_id is ON DELETE CASCADE (R8) — let the DB cascade rather than
        # SQLAlchemy pre-emitting its own DELETEs.
        passive_deletes=True,
    )
