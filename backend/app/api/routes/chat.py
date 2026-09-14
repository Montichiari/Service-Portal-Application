"""Chat endpoints (T-CHAT-0; specs/chatbot/design.md §8, CHAT-1 .. CHAT-14).

Two routes, and **neither takes a conversation id** (CHAT-2). Each user has
exactly one conversation (decision 2), so ownership is implied entirely by
``get_current_user``: there is no id in either URL, no id in either body, and
therefore none of the 404-vs-403 reasoning the ``{id}``-based resources needed.
The whole class of cross-user id leak is absent rather than defended against,
which is the point of the decision and worth reading the signatures below for —
the absence is the contract.

Everything the assistant actually does lives in ``app/chat/``. These handlers
resolve the caller, hand off, and serialise — the same division the other
routers keep, for the same reason: an endpoint is a transport detail and the
conversation is not.

**``POST`` does not work yet, by design.** ``get_model_client`` raises until
T-CHAT-1 supplies an implementation, so the route answers XC-14's ``500``
envelope in a deployment without one. tasks.md splits the phase exactly there:
the schema, both endpoints, tool execution, the trust boundary and persistence
are all finished and tested against a stubbed client here, and the live call —
with the API key and model id it needs — arrives next.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Pagination, get_current_user, pagination_params
from app.api.schemas.chat import ChatMessageCreate, ChatMessageOut, ChatReply
from app.api.schemas.common import Page
from app.chat.client import ChatModelClient, get_model_client
from app.chat.conversation import run_exchange
from app.database import get_db
from app.db.models import ChatConversation, ChatMessage, User

# The `/api/v1` half of the path is applied at mount time in `create_app()`.
router = APIRouter(prefix="/chat", tags=["chat"])


@router.get(
    "/messages",
    response_model=Page[ChatMessageOut],
    summary="Reload the caller's conversation history",
)
def list_chat_messages(
    pagination: Pagination = Depends(pagination_params),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[ChatMessageOut]:
    """The caller's conversation, oldest first (CHAT-2, CHAT-10, XC-10, XC-11).

    Scoped by a join to the caller's conversation in the ``WHERE`` clause, in
    both the count and the page — the rule every list endpoint here follows.
    It reads as belt-and-braces given that the subquery can only ever match one
    conversation, and it is written this way anyway: the alternative is
    filtering after the fetch, which is the habit that eventually meets a
    resource where it does matter.

    A user who has never sent a message has no conversation row at all — first
    ``POST`` creates it (CHAT-1) — so this answers an empty page rather than a
    404. Nothing is missing; there is simply nothing yet.

    Ordering is ``created_at`` then ``id``, the total order CHAT-10 needs so a
    ``tool_result`` cannot come back ahead of the ``tool_use`` it answers. See
    ``ChatMessage.created_at`` for why the column defaults to
    ``clock_timestamp()``.
    """
    conversation_ids = select(ChatConversation.id).where(
        ChatConversation.user_id == user.id
    )
    conditions = [ChatMessage.conversation_id.in_(conversation_ids)]

    total = db.execute(
        select(func.count()).select_from(ChatMessage).where(*conditions)
    ).scalar_one()

    rows = (
        db.execute(
            select(ChatMessage)
            .where(*conditions)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )
        .scalars()
        .all()
    )

    return Page[ChatMessageOut](
        items=[ChatMessageOut.model_validate(row) for row in rows],
        total=total,
        page=pagination.page,
        # The clamped value, not what was asked for (XC-11).
        page_size=pagination.page_size,
    )


@router.post(
    "/messages",
    response_model=ChatReply,
    summary="Send a message to the assistant and get its reply",
)
def send_chat_message(
    payload: ChatMessageCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    client: ChatModelClient = Depends(get_model_client),
) -> ChatReply:
    """Run one exchange and return the assistant's final text (design.md §3).

    ``200``, not the ``201`` the other writes here return. Rows are certainly
    created, but nothing in this response is a created resource: the body is
    the assistant's reply, there is no id to hand back, and no URL addresses
    what was written (§8 gives the conversation no id of its own). A ``201``
    would promise a location that does not exist.

    Synchronous, so the request is held open for the whole call-execute-reply
    loop and the widget shows a pending state meanwhile (design.md §9).
    Streaming is a deliberate later improvement rather than an oversight —
    building it alongside tool calling would mix two new mechanisms in one
    pass.

    ``client`` is a dependency rather than something constructed here, which is
    what lets the tests drive this route with fixed model payloads and what
    will let T-CHAT-1 wire the real one in without touching this handler.
    """
    return ChatReply(
        reply=run_exchange(db, user=user, text=payload.message, client=client)
    )
