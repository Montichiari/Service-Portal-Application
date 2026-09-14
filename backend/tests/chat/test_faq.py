"""The static FAQ and the size rule that decides how it reaches the model
(T-CHAT-0; CHAT-12, design.md §7 decision 4).

No database. This suite runs with Postgres unreachable, the same property
``tests/core/`` has and for the same reason — the FAQ is a module, which is the
whole of CHAT-12, and a test that needed a database to prove that would be
arguing against itself.
"""

from __future__ import annotations

import pytest

from app.chat import faq as faq_module
from app.chat.faq import (
    FAQ_ENTRIES,
    INLINE_LIMIT,
    FaqEntry,
    faq_prompt_section,
    search_faq,
    search_faq_is_enabled,
)
from app.chat.prompt import build_system_prompt
from app.chat.tools import SEARCH_FAQ, available_tools


def test_the_faq_is_code_not_data() -> None:
    """CHAT-12, stated as what the module is: frozen entries, no row ids.

    The migration side of CHAT-12 — that no table was added — is asserted in
    ``tests/db/test_chat.py`` against the real schema, where a table would
    actually show up.
    """
    assert FAQ_ENTRIES
    assert all(isinstance(entry, FaqEntry) for entry in FAQ_ENTRIES)
    with pytest.raises(Exception):
        # Frozen dataclass: FAQ copy is edited in a commit, not at runtime.
        FAQ_ENTRIES[0].answer = "something else"  # type: ignore[misc]


def test_every_entry_has_a_question_and_an_answer() -> None:
    for entry in FAQ_ENTRIES:
        assert entry.question.strip()
        assert entry.answer.strip()


def test_search_returns_the_entry_a_user_would_mean() -> None:
    results = search_faq("my laptop will not turn on")

    assert results
    assert results[0]["question"] == "My computer will not turn on. What should I try first?"


def test_search_ranks_by_overlap_and_is_stable() -> None:
    """Best match first, and the same answer every time.

    Determinism is the point of a keyword count over a handful of entries: the
    model's behaviour cannot be pinned down, so everything underneath it is
    written to be.
    """
    first = search_faq("password reset")
    second = search_faq("password reset")

    assert first == second
    assert first[0]["question"] == "I forgot my password. How do I reset it?"


def test_search_returns_nothing_for_a_query_of_only_stopwords() -> None:
    """An empty result, not the whole FAQ.

    A query that matched everything would be worse than one that matched
    nothing: the model would be handed ten unrelated answers and would pick
    one.
    """
    assert search_faq("what is it") == []


def test_search_caps_how_much_it_returns() -> None:
    assert len(search_faq("request portal status priority", limit=2)) == 2


def test_the_faq_is_inlined_while_it_is_short() -> None:
    """design.md §7's default state, asserted rather than assumed."""
    assert len(FAQ_ENTRIES) <= INLINE_LIMIT
    assert search_faq_is_enabled() is False

    section = faq_prompt_section()
    for entry in FAQ_ENTRIES:
        assert entry.question in section
        assert entry.answer in section

    assert faq_prompt_section() in build_system_prompt()


def test_the_search_tool_is_not_offered_while_the_faq_is_inlined() -> None:
    assert SEARCH_FAQ not in {tool["name"] for tool in available_tools()}


def test_outgrowing_the_inline_limit_switches_the_faq_to_the_tool(monkeypatch) -> None:
    """The other half of decision 4 — the half nothing exercises today.

    ``search_faq_is_enabled`` derives the switchover from the list's length, so
    the branch that matters is the one that only happens after somebody adds a
    sixteenth entry. Testing only the current state would leave a rule whose
    entire purpose is to fire later completely unexercised until it fires in
    production.
    """
    grown = tuple(
        FaqEntry(question=f"Question {index}?", answer=f"Answer {index}.")
        for index in range(INLINE_LIMIT + 1)
    )
    monkeypatch.setattr(faq_module, "FAQ_ENTRIES", grown)

    assert search_faq_is_enabled() is True
    # Inlining stops...
    assert faq_prompt_section() == ""
    assert "Answer 0." not in build_system_prompt()
    # ...and the tool appears in its place, rather than the FAQ vanishing from
    # the model's reach entirely.
    assert SEARCH_FAQ in {tool["name"] for tool in available_tools()}
    assert "search_faq" in build_system_prompt()
