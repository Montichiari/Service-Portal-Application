"""Status model — maps the ``statuses`` table (design.md DDL, requirement R3)."""

from sqlalchemy import Boolean, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPkMixin


class Status(UUIDPkMixin, Base):
    __tablename__ = "statuses"

    # UUIDPkMixin only: `statuses` is static seed data, so it carries no
    # timestamp columns and no TimestampMixin (design.md mixin table).
    # `name` has no CheckConstraint — the four status names are seed data
    # managed by migration, not an enum (R3).

    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_terminal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
