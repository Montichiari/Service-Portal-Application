"""The system prompt as a string (T-CHAT-0b; CHAT-20, design.md §7).

No database, like the rest of ``tests/chat/`` — this is one function returning
text.

These assertions read the *rendered prompt*, never ``prompt.py``'s constants.
A test that imported ``_FAQ_BOUNDARY`` and asserted it was in
``build_system_prompt()`` would be asserting that a variable is used, and it
would stay green if the boundary paragraph were emptied to ``""``. What CHAT-20
requires is that specific words reach the model, so those words are written out
here.
"""

from __future__ import annotations

from app.chat.faq import FAQ_ENTRIES
from app.chat.prompt import build_system_prompt


def test_the_prompt_states_the_faq_is_everything_it_knows() -> None:
    """CHAT-20's first half: the list is closed, and says so.

    design.md §7's reasoning for making this a requirement rather than a
    nicety: a short FAQ makes a plausible eleventh answer *easier* to invent,
    because everything beside it reads as authoritative.
    """
    prompt = build_system_prompt()

    assert (
        "Those ten questions and answers are everything you know about this "
        "portal" in prompt
    )
    assert "Treat them as a closed list." in prompt


def test_the_prompt_says_what_to_do_outside_the_faq() -> None:
    """CHAT-20's second half — the behaviour, not just the boundary.

    Knowing the list is closed is no use without an instruction for the
    questions that fall outside it. Both halves are asserted separately so
    deleting either one goes red on its own.
    """
    prompt = build_system_prompt()

    assert "you don't have specific guidance on that" in prompt
    assert "offer to log a ticket" in prompt
    assert (
        "Do not fill the gap with\ngeneral troubleshooting advice you were not "
        "given above" in prompt
    )


def test_the_boundary_follows_the_entries_it_describes() -> None:
    """"Those ten" needs the ten in front of it to refer to.

    Ordering is the reason this is asserted rather than assumed: the same
    sentence placed above the list would be pointing at nothing, and every
    substring assertion in this file would still pass.
    """
    prompt = build_system_prompt()

    last_answer = FAQ_ENTRIES[-1].answer
    assert prompt.index(last_answer) < prompt.index("Those ten questions")


def test_the_prompt_still_describes_the_portal_and_the_identity_rule() -> None:
    """T-CHAT-0's content, unchanged — this task edited the FAQ half only."""
    prompt = build_system_prompt()

    assert "a priority of low, medium or\n  high." in prompt
    assert "open, in progress, resolved or closed" in prompt
    assert "You act only for the signed-in user." in prompt
