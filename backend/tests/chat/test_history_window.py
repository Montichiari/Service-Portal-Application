"""CHAT-4's 20-message cap, and the thing that makes it more than a slice
(T-CHAT-1).

No database and no model: ``history_window`` is a pure function over the
content-block arrays ``chat_messages`` stores, which is the level the interesting
failure lives at. Every test here is built around one fact — the Messages API
rejects a history whose first message is a ``tool_result`` orphaned from its
``tool_use`` — so the cases that matter are the ones where the cut lands between
a pair, and ``test_the_naive_slice_would_be_invalid_here`` exists to prove the
fixtures below actually are such cases rather than merely looking like them.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.chat.conversation import (
    MAX_HISTORY_MESSAGES,
    history_window,
)


def user_text(text: str = "Hello?") -> dict[str, Any]:
    return {"role": "user", "content": [{"type": "text", "text": text}]}


def assistant_text(text: str = "Hi.") -> dict[str, Any]:
    return {"role": "assistant", "content": [{"type": "text", "text": text}]}


def assistant_tool_use(call_id: str) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "Let me look."},
            {
                "type": "tool_use",
                "id": call_id,
                "name": "get_request_status",
                "input": {"request_id": "x"},
            },
        ],
    }


def user_tool_result(call_id: str) -> dict[str, Any]:
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": call_id,
                "content": "{}",
                "is_error": False,
            }
        ],
    }


def plain_turn(index: int) -> list[dict[str, Any]]:
    """A question and an answer: two messages, no tools."""
    return [user_text(f"question {index}"), assistant_text(f"answer {index}")]


def tool_turn(index: int, *, rounds: int = 1) -> list[dict[str, Any]]:
    """A question answered after ``rounds`` tool calls: ``2 + 2 * rounds``
    messages."""
    messages = [user_text(f"question {index}")]
    for round_number in range(rounds):
        call_id = f"toolu_{index}_{round_number}"
        messages.append(assistant_tool_use(call_id))
        messages.append(user_tool_result(call_id))
    messages.append(assistant_text(f"answer {index}"))
    return messages


@pytest.fixture
def conversation() -> list[dict[str, Any]]:
    """A conversation whose 20-message tail begins mid-pair.

    The turn lengths are mixed (2, 4 and 6 messages) precisely so the boundary
    does not land tidily on a turn start — with uniform turns, every cut is a
    legal one and this whole function would look unnecessary.
    """
    messages: list[dict[str, Any]] = []
    messages += plain_turn(1)
    messages += tool_turn(2, rounds=2)
    messages += plain_turn(3)
    messages += tool_turn(4)
    messages += tool_turn(5, rounds=2)
    messages += plain_turn(6)
    messages += tool_turn(7)
    return messages


def first_block_types(message: dict[str, Any]) -> list[str]:
    return [block["type"] for block in message["content"]]


def test_the_naive_slice_would_be_invalid_here(conversation) -> None:
    """The fixture is a discriminating case, asserted rather than assumed.

    Without this, every other test in the file could be passing against a
    conversation whose tail happens to start legally — in which case
    ``history_window`` and ``messages[-20:]`` agree and nothing here tests
    anything. This is the check that makes the rest meaningful: the plain slice
    really does open on a ``tool_result``, which is the request the API
    rejects.
    """
    assert len(conversation) > MAX_HISTORY_MESSAGES

    naive = conversation[-MAX_HISTORY_MESSAGES:]

    assert naive[0]["role"] == "user"
    assert "tool_result" in first_block_types(naive[0])


def test_the_window_is_within_the_cap(conversation) -> None:
    """CHAT-4's number, on a conversation long enough for it to bite."""
    window = history_window(conversation)

    assert len(window) <= MAX_HISTORY_MESSAGES
    assert len(window) < len(conversation)


def test_the_window_opens_on_a_message_that_can_start_a_request(
    conversation,
) -> None:
    """The property the API enforces: a user message, and not a tool result."""
    window = history_window(conversation)

    assert window[0]["role"] == "user"
    assert first_block_types(window[0]) == ["text"]


def test_every_tool_result_in_the_window_has_its_tool_use(conversation) -> None:
    """Pairing survives the cut, which is the whole point of the boundary.

    Asserted across the window rather than on the first message alone: a cut
    that lands correctly at the front can still be wrong further in if the
    function ever grows a second rule.
    """
    window = history_window(conversation)

    seen_call_ids: set[str] = set()
    for message in window:
        for block in message["content"]:
            if block["type"] == "tool_use":
                seen_call_ids.add(block["id"])
            if block["type"] == "tool_result":
                assert block["tool_use_id"] in seen_call_ids


def test_it_keeps_as_much_history_as_the_cap_allows(conversation) -> None:
    """The earliest legal start, not merely a legal one.

    "Valid" alone is satisfied by returning the last turn, or nothing at all.
    The window is also meant to carry the most context it can afford, so the
    message one position earlier than the chosen start must be one that could
    not have started a request — otherwise a cheaper answer was available and
    was not taken.
    """
    window = history_window(conversation)

    start = len(conversation) - len(window)
    assert start > 0
    previous = conversation[start - 1]
    assert not (
        previous["role"] == "user"
        and "tool_result" not in first_block_types(previous)
        and len(conversation) - (start - 1) <= MAX_HISTORY_MESSAGES
    )


def test_a_short_conversation_is_replayed_whole() -> None:
    """Below the cap, nothing is dropped — including the first message."""
    messages = plain_turn(1) + tool_turn(2)

    assert history_window(messages) == messages


def test_a_single_turn_is_never_cut_apart() -> None:
    """A turn longer than the cap is sent over-budget rather than broken.

    Unreachable today — ``MAX_TOOL_ROUNDS`` bounds one turn at thirteen
    messages — and it is the behaviour a future tool set must inherit: the
    alternative is a request the API refuses, which costs the user their answer
    rather than a few tokens.
    """
    long_turn = tool_turn(1, rounds=MAX_HISTORY_MESSAGES)

    window = history_window(long_turn)

    assert window == long_turn
    assert len(window) > MAX_HISTORY_MESSAGES


def test_a_history_with_no_legal_start_is_replayed_as_nothing() -> None:
    """The degenerate case answers empty rather than guessing at a cut."""
    orphans = [user_tool_result("toolu_orphan"), assistant_text()]

    assert history_window(orphans) == []


def test_the_cap_is_the_documented_twenty() -> None:
    """Pinned to CHAT-4's literal number, not to the constant under test.

    backend/CLAUDE.md: an expectation derived from the constant it is checking
    asserts self-consistency and would stay green if decision 5 were quietly
    changed. The requirement says twenty, so the test says twenty.
    """
    assert MAX_HISTORY_MESSAGES == 20
