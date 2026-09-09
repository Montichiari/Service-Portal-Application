"""Comment model — maps the ``comments`` table (design.md DDL, requirement R6)."""

import uuid

from sqlalchemy import Boolean, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin


class Comment(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "comments"

    # UUIDPkMixin + TimestampMixin: comments are editable, so both created_at
    # and updated_at apply — unlike the immutable status_history rows (design.md
    # mixin applicability table, R6).

    service_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # CASCADE: a comment has no meaning without its parent request
        # (design.md "ON DELETE behavior", R8).
        ForeignKey("service_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # RESTRICT: a user who authored comments can't be deleted out from
        # under them (design.md "ON DELETE behavior", R8). Type is UUID — the
        # drawio ERD's "(int)" label was a labeling slip (design.md resolved
        # decision #1), matching every other FK to users.id.
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    # --- Relationships --------------------------------------------------------
    # back_populates targets attribute names declared in Tasks 2/3:
    # ServiceRequest.comments and User.comments.
    service_request: Mapped["ServiceRequest"] = relationship(
        "ServiceRequest",
        back_populates="comments",
        # service_request_id is ON DELETE CASCADE (R8) — defer to the DB.
        passive_deletes=True,
    )
    # author_id is the only FK from comments to users, so no foreign_keys=
    # disambiguation is needed here.
    author: Mapped["User"] = relationship(
        "User",
        back_populates="comments",
    )
