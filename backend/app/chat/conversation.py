"""The conversation itself: one per user, and the turn that appends to it
(CHAT-1, CHAT-3, CHAT-8, CHAT-10, CHAT-11; design.md §3).

design.md decision 2 gives each user exactly one continuous conversation, and
``chat_conversations.user_id`` is UNIQUE so that is a fact about the database
rather than a habit of this module. Everything below follows from it: there is
no conversation id to pass, no thread to select, and no ownership check to
write — the row is reached through the authenticated user or not at all
(CHAT-2).

**What is persisted, and when.** The user's message is written and committed
*before* the model is called (CHAT-3), so a failed or slow call cannot lose
what someone typed. Each subsequent message — the assistant's reply, the
``tool_result`` blocks answering its tool calls, the assistant's follow-up — is
committed as it happens, in the Messages API's own shape (CHAT-10): a
``tool_use`` block rides inside an **assistant** message and its ``tool_result``
inside the next **user** message, because the API has no third role
(design.md §2). Storing the content-block array verbatim is what lets a stored
conversation be replayed to the API without reconstruction.

**What is deliberately not here.** The call itself. ``client`` is a
``ChatModelClient`` the caller resolves, and in T-CHAT-0 there is no
implementation of one — the loop below is exercised by stubs returning fixed
payloads, which is the split tasks.md drew and the reason none of this needs an
API key. Capping the replayed history at the last 20 messages (CHAT-4) belongs
with the live call in T-CHAT-1, and is the one thing a reader should expect to
see appear here later.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.chat.client import STOP_REASON_TOOL_USE, ChatModelClient
from app.chat.prompt import build_system_prompt
from app.chat.tools import available_tools, execute_tool
from app.db.models import ChatConversation, ChatMessage, User

logger = logging.getLogger(__name__)

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"

# How many times one user message may lead to another round of tool calls
# before the loop gives up. CHAT-11 says "repeat until end_turn", which on its
# own is unbounded: a model that answers every tool_result with another
# tool_use would hold the request open indefinitely, and every round is a
# metered API call. Five is far more than any tool set this size needs — two
# rounds covers "look the request up, then file a new one" — and the ceiling
# exists for the pathological case, not the normal one.
MAX_TOOL_ROUNDS = 5

# Sent when the ceiling above is hit. Phrased for the person reading it, since
# by definition the model is not going to summarise anything at this point.
TOOL_LOOP_EXHAUSTED_REPLY = (
    "Sorry — I got stuck working on that and stopped before going in circles. "
    "Could you try asking again, more specifically?"
)

# Sent when a turn ends with no text block at all. A model that stops with an
# empty reply is not a state worth crashing over, but returning "" would leave
# the widget showing a blank bubble with no way to tell it from a rendering
# bug.
EMPTY_REPLY = (
    "Sorry — I did not manage to put an answer together. Could you rephrase "
    "that?"
)


def get_or_create_conversation(db: Session, user: User) -> ChatConversation:
    """The caller's one conversation, created on first use (CHAT-1).

    The ``IntegrityError`` branch is not defensive padding: two messages sent
    close together — a double-clicked send button, a widget retrying — race
    here, and without the UNIQUE constraint they would produce two
    conversations and split the user's history between them. With it, the loser
    of the race fails its INSERT and reads the winner's row, which is why the
    constraint is worth more than the check that precedes it.
    """
    existing = db.execute(
        select(ChatConversation).where(ChatConversation.user_id == user.id)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    conversation = ChatConversation(user_id=user.id)
    db.add(conversation)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.execute(
            select(ChatConversation).where(ChatConversation.user_id == user.id)
        ).scalar_one()
    db.refresh(conversation)
    return conversation


def conversation_messages(
    db: Session, conversation: ChatConversation
) -> list[ChatMessage]:
    """Every message in the conversation, oldest first.

    The order is ``created_at`` then ``id``, and both halves are needed: the
    timestamp is the real key, and the id breaks ties the way every other list
    in this API breaks them. ``chat_messages.created_at`` defaults to
    ``clock_timestamp()`` rather than ``now()`` precisely so the timestamp can
    separate rows written inside one transaction — see the model, where the
    reasoning belongs.
    """
    return list(
        db.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation.id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        )
        .scalars()
        .all()
    )


def append_message(
    db: Session,
    conversation: ChatConversation,
    *,
    role: str,
    content: list[dict[str, Any]],
) -> ChatMessage:
    """Append one message and commit it (CHAT-10).

    Committed per message rather than once at the end of the turn. A single
    commit would be tidier and is wrong for this table: CHAT-3 requires the
    user's text to survive a failing model call, and the same argument applies
    to every block after it — a turn that dies half way through should leave
    the half that happened, not erase the tool call that already created a real
    service request.
    """
    message = ChatMessage(
        conversation_id=conversation.id, role=role, content=content
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def to_model_messages(rows: Sequence[ChatMessage]) -> list[dict[str, Any]]:
    """Stored rows as a Messages API ``messages`` array.

    A rename, not a transformation: ``content`` is handed back exactly as it
    was stored. That is the property that makes JSONB worth its awkwardness
    here (design.md §6) — anything this function had to rebuild would be
    something a stored conversation could no longer replay faithfully.
    """
    return [{"role": row.role, "content": row.content} for row in rows]


def _text_from(content: Sequence[dict[str, Any]]) -> str:
    """The text blocks of one assistant message, joined.

    design.md §3 step 8 returns *only* the final assistant text to the
    frontend: a ``tool_use`` block in the same message is machinery the widget
    has no use for, and the id it carries is not a service request's.
    """
    return "\n\n".join(
        str(block.get("text", ""))
        for block in content
        if block.get("type") == "text" and block.get("text")
    ).strip()


def _tool_use_blocks(content: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [block for block in content if block.get("type") == "tool_use"]


def run_exchange(
    db: Session,
    *,
    user: User,
    text: str,
    client: ChatModelClient,
) -> str:
    """One user message in, the assistant's final text out (design.md §3).

    The loop is CHAT-11's: call, and if the response stopped to use tools,
    execute them, hand the results back, and call again — until the model stops
    for any other reason. Every tool runs against ``user``; ``execute_tool``
    takes no identity from the model's arguments (CHAT-7) and turns a failure
    into a ``tool_result`` the model can recover from rather than an exception
    the user sees (CHAT-8).

    Note the order inside each iteration: the assistant's message is persisted
    *before* its tool calls are executed. A tool that writes a row and then
    crashes the process must not leave a conversation with no record of what
    asked for it.
    """
    conversation = get_or_create_conversation(db, user)

    # CHAT-3. Committed before the call below, so a model that times out, errors
    # or answers slowly cannot cost someone the message they typed.
    append_message(
        db,
        conversation,
        role=ROLE_USER,
        content=[{"type": "text", "text": text}],
    )

    system = build_system_prompt()
    tools = available_tools()

    for _ in range(MAX_TOOL_ROUNDS + 1):
        response = client.create_message(
            system=system,
            tools=tools,
            messages=to_model_messages(conversation_messages(db, conversation)),
        )

        content = list(response.content or ())
        if content:
            append_message(
                db, conversation, role=ROLE_ASSISTANT, content=content
            )

        if response.stop_reason != STOP_REASON_TOOL_USE:
            # Any stop reason that is not `tool_use` ends the turn — `end_turn`
            # normally, but also `max_tokens` and anything this code has not
            # heard of. Treating an unknown reason as "over" is the safe
            # direction: the user gets a short answer, where the other reading
            # would execute tool calls off a response that made none.
            return _text_from(content) or EMPTY_REPLY

        calls = _tool_use_blocks(content)
        if not calls:
            # `tool_use` with no `tool_use` block. Nothing to execute and
            # nothing to send back, so calling again would replay the identical
            # history and stop the same way.
            logger.warning(
                "Model reported stop_reason=tool_use with no tool_use block "
                "(conversation %s)",
                conversation.id,
            )
            return _text_from(content) or EMPTY_REPLY

        results = [execute_tool(call, db=db, user=user) for call in calls]
        # Results go back as a **user** message: the Messages API has no tool
        # role, and a `tool_result` block is only valid inside a user turn
        # (design.md §2). One message carrying every result, in the order the
        # calls appeared, because the API pairs them by `tool_use_id` and
        # expects them together.
        append_message(db, conversation, role=ROLE_USER, content=results)

    logger.warning(
        "Chat exchange hit MAX_TOOL_ROUNDS=%s (conversation %s)",
        MAX_TOOL_ROUNDS,
        conversation.id,
    )
    return TOOL_LOOP_EXHAUSTED_REPLY
