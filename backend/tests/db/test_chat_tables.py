"""Schema contract tests for ``chat_conversations`` and ``chat_messages``
(app/db/models/chat_*.py; specs/chatbot/design.md §6, T-CHAT-0).

Against the real Postgres test database, like the rest of this package — the
three things asserted below are a ``CHECK``, a ``UNIQUE`` and two ``ON DELETE``
rules, none of which SQLite would enforce the same way, plus one property
(``clock_timestamp()`` advancing inside a transaction) that no other database
reproduces at all.

Each of these was confirmed to fail with its subject removed before being kept:
the CHECK dropped, the UNIQUE dropped, the cascades switched to ``RESTRICT``
and the default switched back to ``now()``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, func, inspect, select
from sqlalchemy.exc import IntegrityError

from app.db.models import ChatConversation, ChatMessage, User


@pytest.fixture
def conversation(db_session, make_user) -> ChatConversation:
    row = ChatConversation(user_id=make_user().id)
    db_session.add(row)
    db_session.flush()
    return row


def add_message(db_session, conversation, **overrides) -> ChatMessage:
    fields = dict(
        conversation_id=conversation.id,
        role="user",
        content=[{"type": "text", "text": "hello"}],
    )
    fields.update(overrides)
    message = ChatMessage(**fields)
    db_session.add(message)
    db_session.flush()
    return message


def test_role_is_constrained_to_the_two_messages_api_roles(
    db_session, conversation
):
    """The Messages API has no third role (design.md §2).

    A ``tool_result`` rides inside a ``user`` message and a ``tool_use`` inside
    an ``assistant`` one, so a row claiming ``role='tool'`` could not be
    replayed to the API — the constraint is about what the conversation can be
    reconstructed into, not about tidiness.
    """
    with pytest.raises(IntegrityError):
        add_message(db_session, conversation, role="tool")


def test_a_user_cannot_have_two_conversations(db_session, conversation):
    """Decision 2, as a constraint rather than as a convention.

    ``get_or_create_conversation`` checks before it inserts, and that check
    loses a race between two messages sent at once. This is what makes the
    loser fail instead of splitting the user's history across two rows.
    """
    duplicate = ChatConversation(user_id=conversation.user_id)
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_a_conversation_takes_its_messages(db_session, conversation):
    """ON DELETE CASCADE: a message has no meaning without its conversation."""
    add_message(db_session, conversation)
    add_message(db_session, conversation, role="assistant")

    # Core DELETE so the database's own rule is what is exercised, not
    # SQLAlchemy's cascade.
    db_session.execute(
        delete(ChatConversation).where(ChatConversation.id == conversation.id)
    )

    remaining = db_session.execute(
        select(func.count())
        .select_from(ChatMessage)
        .where(ChatMessage.conversation_id == conversation.id)
    ).scalar_one()
    assert remaining == 0


def test_deleting_a_user_takes_their_conversation(db_session, conversation):
    """ON DELETE CASCADE from ``users`` — deliberately unlike ``comments``.

    A filed request and an authored comment are RESTRICT because they are part
    of the service history other people rely on. A chat thread is per-user
    machinery, like a refresh token: nothing outside this user's own widget
    reads it, and keeping it after the account is gone would preserve a private
    transcript for nobody's benefit.
    """
    add_message(db_session, conversation)

    db_session.execute(delete(User).where(User.id == conversation.user_id))

    assert (
        db_session.execute(
            select(func.count())
            .select_from(ChatConversation)
            .where(ChatConversation.id == conversation.id)
        ).scalar_one()
        == 0
    )


def test_a_content_block_array_survives_the_round_trip(db_session, conversation):
    """CHAT-10's storage half: JSONB in, the identical array out.

    The whole argument for JSONB over text (design.md §6) is that a stored
    conversation can be replayed to the API without reconstruction. A round
    trip that reordered keys or stringified a nested object would break that
    quietly — the transcript would still *read* correctly.
    """
    blocks = [
        {"type": "text", "text": "Filing that now."},
        {
            "type": "tool_use",
            "id": "toolu_01",
            "name": "create_service_request",
            "input": {
                "title": "Laptop will not power on",
                "description": "No lights.",
                "priority": "high",
            },
        },
    ]
    message = add_message(
        db_session, conversation, role="assistant", content=blocks
    )

    db_session.expire(message)
    assert message.content == blocks


def test_created_at_advances_within_one_transaction(db_session, conversation):
    """``clock_timestamp()``, not ``now()`` — and this is the test that says so.

    A turn appends four rows in quick succession, and CHAT-10 needs them back
    in the order they were written. Under ``now()``
    (``transaction_timestamp()``) every row written in one transaction shares a
    timestamp, ``ORDER BY created_at`` falls through to a random-UUID
    tiebreaker, and a ``tool_result`` can come back ahead of the ``tool_use``
    it answers — which the Messages API rejects on replay.

    Written as four rows in **one** transaction because that is the case
    ``now()`` gets wrong; a test that committed between them would pass either
    way.
    """
    rows = [add_message(db_session, conversation) for _ in range(4)]
    for row in rows:
        db_session.refresh(row)

    stamps = [row.created_at for row in rows]
    assert stamps == sorted(stamps)
    assert len(set(stamps)) == 4

    ordered = (
        db_session.execute(
            select(ChatMessage.id)
            .where(ChatMessage.conversation_id == conversation.id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        )
        .scalars()
        .all()
    )
    assert ordered == [row.id for row in rows]


def test_no_migration_added_an_faq_table(engine):
    """CHAT-12, asserted where a table would actually appear.

    The FAQ lives in ``app/chat/faq.py`` and is reviewed with the code that
    reads it. This is the half of that requirement a module-level test cannot
    make: it reads the migrated database rather than the source tree, so a
    later revision quietly adding a ``faqs`` table turns it red.
    """
    tables = set(inspect(engine).get_table_names())

    assert {"chat_conversations", "chat_messages"} <= tables
    assert not [name for name in tables if "faq" in name.lower()]
