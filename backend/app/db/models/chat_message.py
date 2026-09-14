"""ChatMessage model — maps the ``chat_messages`` table
(specs/chatbot/design.md §6, T-CHAT-0).

``content`` is the raw Anthropic content-block **array** for one message, kept
as JSONB rather than text. The Messages API has no separate "tool" role: a tool
call is a ``tool_use`` block inside an assistant message and its outcome is a
``tool_result`` block inside the next user message (design.md §2), so the shape
genuinely varies per row and a flat text column could only store a lossy
rendering of it. Storing the array verbatim is what lets a stored conversation
be replayed back to the API without reconstruction (CHAT-10).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import UUIDPkMixin


class ChatMessage(UUIDPkMixin, Base):
    __tablename__ = "chat_messages"

    # UUIDPkMixin only — no TimestampMixin. A message is appended and never
    # edited, so `created_at` alone is the whole story, the same call
    # `status_history` and `refresh_tokens` made (design.md §6 lists exactly
    # these four columns).

    # `role` is a VARCHAR + CheckConstraint, never a native Postgres ENUM
    # (locked decision — backend/CLAUDE.md). The two values are the Messages
    # API's own roles, and there is no third: a `tool_result` rides inside a
    # `user` message and a `tool_use` inside an `assistant` one.
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="role_valid"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # CASCADE: a message has no meaning without its conversation, the same
        # reasoning `comments.service_request_id` records.
        ForeignKey("chat_conversations.id", ondelete="CASCADE"),
        nullable=False,
        # Indexed: every read of this table is "this conversation's messages,
        # in order", and every write is preceded by one.
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    # A JSON *array* of content blocks, not an object — `Mapped[list[Any]]`
    # rather than the `Mapped[dict]` on `service_requests.request_metadata`.
    # No server default: a message with no blocks is not a state this table
    # should be able to reach, so there is nothing sensible to default to.
    content: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    # Plain (non-mixin) timestamp column — DateTime(timezone=True) explicit for
    # the same reason as StatusHistory.changed_at: a bare Mapped[datetime]
    # resolves to TIMESTAMP WITHOUT TIME ZONE, not TIMESTAMPTZ.
    #
    # `clock_timestamp()`, **not** the `now()` every other table here defaults
    # to, and this one is load-bearing rather than stylistic. `now()` is
    # `transaction_timestamp()`: every row written inside one transaction gets
    # the same value. This is the one table that appends several rows per unit
    # of work — a turn is user text, then an assistant `tool_use`, then a
    # `tool_result`, then the assistant's reply — so under `now()` those four
    # rows would be indistinguishable by timestamp and `ORDER BY created_at`
    # would fall through to the tiebreaker, which is a random UUID. CHAT-10
    # asks for the blocks back *in order*, and a reconstruction that put a
    # `tool_result` before the `tool_use` it answers is not merely untidy: the
    # Messages API rejects it. `clock_timestamp()` advances within a
    # transaction, so (created_at, id) is a total order in the sequence the
    # rows were actually written.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("clock_timestamp()"),
        nullable=False,
    )

    # --- Relationships --------------------------------------------------------
    conversation: Mapped["ChatConversation"] = relationship(
        "ChatConversation",
        back_populates="messages",
        # conversation_id is ON DELETE CASCADE — defer to the DB.
        passive_deletes=True,
    )
