"""Chat schemas (T-CHAT-0; specs/chatbot/design.md §8, CHAT-10, CHAT-14).

Neither shape here carries a conversation id, and that is the contract rather
than an omission: each user has exactly one conversation (decision 2), so
ownership is implied by the session and there is no id for a caller to send,
guess or be refused (CHAT-2). ``UserSummary`` is not embedded either — every
message in a conversation is either the caller's or the assistant's, so a
``role`` says everything an author field would.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.common import UTCDateTime

# CHAT-14 / decision 6. Generous for a support request — a few thousand
# characters is a long paragraph of error output — and cheap to raise, which is
# the reason the number is here rather than argued about. It bounds both cost
# and misuse: every character is replayed to the model on every subsequent call
# of the conversation, so an unbounded message is an unbounded recurring bill.
MAX_MESSAGE_CHARS = 4000


class ChatMessageCreate(BaseModel):
    """``POST /chat/messages`` body."""

    # `extra="ignore"`, matching `ServiceRequestCreate`: a client sending a
    # `conversation_id` — the field this API deliberately does not have — gets
    # the same conversation it would have got without it, rather than a 422
    # that reads as though the field were merely misspelled.
    model_config = ConfigDict(extra="ignore")

    # The ceiling is enforced here, in the validation layer, so CHAT-14's
    # rejection is XC-4's envelope with `fields.message` populated and arrives
    # before the message is persisted or a single token is spent. Truncating
    # instead would be worse than either: the user would be answered about a
    # question they did not finish asking.
    message: Annotated[str, Field(min_length=1, max_length=MAX_MESSAGE_CHARS)]


class ChatReply(BaseModel):
    """``POST /chat/messages`` response — the final assistant text, and no more.

    design.md §3 step 8: the tool calls, their results and the intermediate
    turns are all persisted and all readable through ``GET /chat/messages``, but
    what the widget shows is the answer. Returning the raw block array here
    would make the frontend responsible for knowing which blocks are machinery.
    """

    reply: str


class ChatMessageOut(BaseModel):
    """One stored message, blocks and all (CHAT-10)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # `user` or `assistant` — the Messages API's two roles. A `tool_result`
    # rides inside a `user` message and a `tool_use` inside an `assistant` one
    # (design.md §2), so a reader wanting to know which is which reads the
    # blocks, not this field.
    role: str
    # The content-block array exactly as stored. Typed loosely on purpose: the
    # block types are Anthropic's, they differ per block, and a stricter model
    # here would have to be revised every time the API gained one — while
    # silently dropping the blocks it did not recognise from a response whose
    # entire job is to be a faithful transcript.
    content: list[dict[str, Any]]
    created_at: UTCDateTime
