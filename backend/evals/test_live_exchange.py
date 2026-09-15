"""T-CHAT-1's first three acceptance criteria, against a live model.

These are the ones a stub cannot answer. ``tests/api/test_chat.py`` already
proves that a ``tool_use`` payload is validated, executed for the authenticated
user and persisted in order — what it cannot prove is that a real model,
handed the real system prompt and the real tool descriptions, decides to make
that call at all, and that what comes back out of a live round trip still fits
through the loop.

Each test prints the transcript it produced. That is not decoration: when one
of these fails, the reply and the block sequence are the evidence, and a bare
assertion error would throw them away.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy import select

from app.chat.client import ModelResponse
from app.chat.conversation import (
    conversation_messages,
    get_or_create_conversation,
    run_exchange,
)
from app.db.models import ServiceRequest


def print_transcript(db, user, *, label: str) -> list[dict[str, Any]]:
    """Every stored block of the caller's conversation, in order.

    Exactly what ``GET /chat/messages`` would return, read back from the
    database rather than from anything the loop kept in memory.
    """
    conversation = get_or_create_conversation(db, user)
    rows = conversation_messages(db, conversation)

    print(f"\n===== transcript: {label}")
    for row in rows:
        for block in row.content:
            kind = block.get("type")
            if kind == "text":
                print(f"  [{row.role}/text] {block['text']}")
            elif kind == "tool_use":
                print(
                    f"  [{row.role}/tool_use] {block['name']} "
                    f"{json.dumps(block['input'])}"
                )
            elif kind == "tool_result":
                flag = "ERROR" if block.get("is_error") else "ok"
                print(f"  [{row.role}/tool_result {flag}] {block['content']}")
            else:
                print(f"  [{row.role}/{kind}] {json.dumps(block)[:200]}")
    print("=====")

    return [block for row in rows for block in row.content]


def tool_calls(blocks: list[dict[str, Any]]) -> list[str]:
    return [block["name"] for block in blocks if block.get("type") == "tool_use"]


# --- CHAT-6 / CHAT-11: a live tool call writes a real row --------------------


def test_asking_for_a_ticket_files_one(db_session, make_user, live_client) -> None:
    """The acceptance criterion, end to end and for real.

    Three things have to hold at once and only a live call can produce them
    together: the model chooses ``create_service_request`` off the real prompt,
    the row it writes belongs to the authenticated user (CHAT-7 — nothing in
    the message says who is asking), and the loop comes back with a
    natural-language reply rather than the tool's JSON.

    What is *not* asserted is any of the reply's wording. design.md §11: the
    reply is a sample, the tool choice and the row are facts.
    """
    user = make_user()

    reply = run_exchange(
        db_session,
        user=user,
        text=(
            "My laptop won't turn on at all — no lights, nothing. I've tried a "
            "different power outlet. Please file a ticket for this."
        ),
        client=live_client,
    )

    blocks = print_transcript(db_session, user, label="create a ticket")
    print(f"[reply] {reply}")

    assert "create_service_request" in tool_calls(blocks)

    requests = list(
        db_session.execute(
            select(ServiceRequest).where(ServiceRequest.requestor_id == user.id)
        )
        .scalars()
        .all()
    )
    assert len(requests) == 1, "expected exactly one request to have been filed"
    created = requests[0]
    assert created.requestor_id == user.id
    assert created.assignee_id is None
    assert created.title
    assert created.description
    assert created.current_status.name == "open"

    # A reply the user can read, not a serialised tool result. Asserting the
    # shape of the answer rather than its content: non-empty, and not the JSON
    # the tool handed back.
    assert reply.strip()
    assert not reply.strip().startswith("{")


# --- the first round trip answers an FAQ with no tool at all -----------------


def test_an_faq_question_is_answered_without_a_tool_call(
    db_session, make_user, live_client
) -> None:
    """The acceptance criterion's third line: one round trip, no tool.

    The failure this guards against is a prompt that makes the assistant file a
    ticket for every message — a plausible way to be wrong that every
    deterministic test in the suite would pass, since a stub only ever does
    what the test told it to.
    """
    user = make_user()

    reply = run_exchange(
        db_session,
        user=user,
        text="How do I reset my password?",
        client=live_client,
    )

    blocks = print_transcript(db_session, user, label="FAQ question")
    print(f"[reply] {reply}")

    assert tool_calls(blocks) == []
    assert reply.strip()
    # Nothing was filed for a question that was only asked.
    assert (
        db_session.execute(
            select(ServiceRequest).where(ServiceRequest.requestor_id == user.id)
        )
        .scalars()
        .first()
        is None
    )


# --- CHAT-3: the user's message is written before the call -------------------


@dataclass
class FailingLiveClient:
    """The real client, aimed at a credential that will be rejected.

    Closer to the criterion than a stub that raises: the acceptance criterion
    says "force the API call to fail", and the failure this produces is a real
    one from the real transport — the SDK's own exception, raised from the same
    line a network outage or an expired key would raise it from.
    """

    inner: Any

    def create_message(self, **kwargs: Any) -> ModelResponse:
        broken = self.inner.sdk.copy(api_key="not-a-valid-key")
        return type(self.inner)(
            sdk=broken, model=self.inner.model, max_tokens=self.inner.max_tokens
        ).create_message(**kwargs)


def test_the_typed_message_survives_a_failing_live_call(
    db_session, make_user, live_client
) -> None:
    """CHAT-3, verified the way the acceptance criterion asks for.

    On a successful call, "persisted before" and "persisted after" look
    identical. Only a failure separates them, and the property matters most
    exactly then: a user whose message vanished because a call failed has lost
    something they typed.
    """
    user = make_user()
    text = "My VPN keeps dropping every few minutes."

    with pytest.raises(Exception) as raised:  # noqa: PT011 - any transport failure
        run_exchange(
            db_session,
            user=user,
            text=text,
            client=FailingLiveClient(inner=live_client),
        )

    print(f"\n[forced failure] {type(raised.value).__name__}: {str(raised.value)[:200]}")
    blocks = print_transcript(db_session, user, label="failed call")

    assert blocks == [{"type": "text", "text": text}]
