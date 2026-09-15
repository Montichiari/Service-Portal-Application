"""design.md §11's eval set: fixed messages, expected *tool choice* (T-CHAT-1).

Not a test suite in the usual sense. The subject is the system prompt and the
tool descriptions — whether they steer a real model to the right call — and the
thing being measured is a decision, not an output. So every case below asserts
which tool the model reached for (or that it reached for none) and nothing
whatsoever about what it said.

Each case is one Messages API call with no tool execution and no database: the
choice is visible in the first response, and executing the call would only add
cost and a second thing to go wrong. That also means the ``request_id`` in the
lookup cases need not exist — the model is being asked to *decide*, not to
succeed.

Run it when the system prompt or a tool description changes, which is when
routing can regress silently. Not on every push: it costs money and, being a
sample of a distribution, it can be flaky in both directions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

CREATE = "create_service_request"
LOOKUP = "get_request_status"
NO_TOOL = None


@dataclass(frozen=True)
class Case:
    """One message, one expected decision, and why it is expected."""

    id: str
    message: str
    expected: str | None
    why: str


CASES = [
    # --- filing ---------------------------------------------------------------
    Case(
        id="explicit-request",
        message="Please open a ticket: my monitor flickers every few minutes.",
        expected=CREATE,
        why="The user asked for a ticket in so many words.",
    ),
    Case(
        id="blocked-with-no-workaround",
        message=(
            "My computer won't turn on. I've checked the cable and held the "
            "power button down. I have a client call in an hour."
        ),
        expected=CREATE,
        why=(
            "FAQ 6 covers the checks and the user has already done them, so the "
            "prompt's 'file once troubleshooting has not resolved it' applies."
        ),
    ),
    # --- looking up -----------------------------------------------------------
    Case(
        id="status-by-id",
        message=(
            "What's the status of request "
            "3f4b2c1e-9d7a-4a58-8f2e-1c0b7d5a6e34?"
        ),
        expected=LOOKUP,
        why="An id in hand and a question about its status is the tool's case.",
    ),
    # --- answering from the FAQ ----------------------------------------------
    Case(
        id="faq-password",
        message="How do I reset my password?",
        expected=NO_TOOL,
        why="FAQ 1 answers it outright; a ticket here would be noise.",
    ),
    Case(
        id="faq-response-time",
        message="How long does it usually take to get a response on a ticket?",
        expected=NO_TOOL,
        why="FAQ 9, verbatim.",
    ),
    Case(
        id="faq-vpn-first-step",
        message="My VPN won't connect. What should I try first?",
        expected=NO_TOOL,
        why=(
            "FAQ 2 gives the first steps, and the prompt says to try the obvious "
            "checks before filing — so the first turn should advise, not file."
        ),
    ),
    # --- the grounding boundary (CHAT-20) ------------------------------------
    Case(
        id="outside-the-faq",
        message="What's our company's parental leave policy?",
        expected=NO_TOOL,
        why=(
            "Outside the ten entries and outside IT entirely. CHAT-20 asks for a "
            "decline plus an offer, not a filed ticket and not an invented "
            "answer."
        ),
    ),
]


def chosen_tool(response) -> str | None:
    """The tool the model reached for, if any.

    Deliberately tolerant of more than one block: the API may return text and a
    ``tool_use`` together, and the case's expectation is about the call, not
    about whether the model narrated it.
    """
    calls = [block for block in response.content if block.get("type") == "tool_use"]
    if not calls:
        return None
    return calls[0]["name"]


def reply_text(response) -> str:
    return " ".join(
        block.get("text", "")
        for block in response.content
        if block.get("type") == "text"
    ).strip()


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_the_model_picks_the_expected_tool(
    case: Case, live_client, system_prompt, tools: list[dict[str, Any]]
) -> None:
    """One call, one decision, asserted against ``case.expected`` alone."""
    response = live_client.create_message(
        system=system_prompt,
        tools=tools,
        messages=[{"role": "user", "content": [{"type": "text", "text": case.message}]}],
    )

    actual = chosen_tool(response)

    print(f"\n[{case.id}] {case.message}")
    print(f"  expected: {case.expected or 'no tool'}   actual: {actual or 'no tool'}")
    print(f"  stop_reason: {response.stop_reason}")
    print(f"  said: {reply_text(response) or '(nothing)'}")

    assert actual == case.expected, case.why
