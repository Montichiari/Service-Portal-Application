"""ChatConversation model — maps the ``chat_conversations`` table
(specs/chatbot/design.md §6, T-CHAT-0).

One row per user, forever: decision 2 in design.md §10 settles on a single
continuous conversation rather than a thread list, and the ``UNIQUE`` on
``user_id`` is what makes that a schema guarantee instead of a convention the
endpoints are trusted to keep. It is also why no chat URL carries a
conversation id (§8) — there is never a second row to address.
"""

import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin


class ChatConversation(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "chat_conversations"

    # UUIDPkMixin + TimestampMixin, matching design.md §6's four columns.
    # `updated_at` earns its place here where it doesn't on `chat_messages`:
    # the conversation is a long-lived container that changes every time a
    # message is appended, while a message itself is written once.

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # CASCADE, the same call `refresh_tokens` made and deliberately not the
        # RESTRICT that `comments.author_id` and `service_requests.requestor_id`
        # use. The distinction is whether the row is a record *of* the user or a
        # record *about* the work: a filed request and an authored comment are
        # part of the service history other people rely on, and must not vanish
        # with the account. A chat thread is per-user machinery, like a session
        # token — nothing outside this user's own widget ever reads it.
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        # UNIQUE (design.md §6), not merely indexed: the get-or-create in
        # `app/chat/conversation.py` is the only writer today, and a race
        # between two concurrent first messages would otherwise create two
        # rows and split the user's history in half. The index a UNIQUE
        # constraint builds also serves the by-user lookup every chat request
        # starts with, so this is not a second index alongside one.
        unique=True,
    )

    # --- Relationships --------------------------------------------------------
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="conversation",
        # chat_messages.conversation_id is ON DELETE CASCADE — let the database
        # cascade rather than SQLAlchemy pre-emitting its own DELETEs.
        passive_deletes=True,
    )
    # back_populates targets User.chat_conversation, added in this same task.
    # Only one FK from here to users, so no foreign_keys= disambiguation.
    user: Mapped["User"] = relationship(
        "User",
        back_populates="chat_conversation",
        passive_deletes=True,
    )
