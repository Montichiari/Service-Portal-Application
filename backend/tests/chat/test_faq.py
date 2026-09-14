"""The static FAQ and the prompt it is inlined into (T-CHAT-0b; CHAT-12,
CHAT-20, design.md §7 decision 4).

No database. This suite runs with Postgres unreachable, the same property
``tests/core/`` has and for the same reason — the FAQ is a module, which is the
whole of CHAT-12, and a test that needed a database to prove that would be
arguing against itself.

What changed in T-CHAT-0b: the size-threshold tests are gone along with the
threshold. There is no entry-count limit to sit under and no tool to switch to,
so the assertions here are about the content being the ten entries design.md
fixed and about all ten reaching the model every time.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.chat.faq import FAQ_ENTRIES, FaqEntry, faq_prompt_section
from app.chat.prompt import build_system_prompt

DESIGN_MD = Path(__file__).resolve().parents[3] / "specs" / "chatbot" / "design.md"


def _entries_from_design_md() -> list[tuple[str, str]]:
    """design.md §7's ten entries, parsed out of the document itself.

    The alternative — a second hand-typed copy of the ten answers in this file
    — would be two transcriptions of one source, and a test comparing them
    would pass whenever they drift together and fail whenever someone fixes a
    typo in only one. "Copied verbatim" is a claim about the relationship
    between the module and the design document, so the document is what this
    reads.
    """
    text = DESIGN_MD.read_text(encoding="utf-8")
    block = text[
        text.index("Content (copy verbatim") : text.index("Grounding boundary")
    ]
    entries = []
    for item in re.split(r"\n(?=\s*\d+\.\s+\*\*)", block):
        if not re.match(r"\s*\d+\.\s+\*\*", item):
            continue
        flat = " ".join(line.strip() for line in item.strip().splitlines())
        match = re.match(r"\d+\.\s+\*\*(.+?)\*\*\s+(.*)$", flat, re.S)
        assert match is not None, flat[:80]
        entries.append((match.group(1).strip(), match.group(2).strip()))
    return entries


def test_the_faq_is_code_not_data() -> None:
    """CHAT-12, stated as what the module is: frozen entries, no row ids.

    The migration side of CHAT-12 — that no table was added — is asserted in
    ``tests/db/test_chat_tables.py`` against the real schema, where a table
    would actually show up.
    """
    assert FAQ_ENTRIES
    assert all(isinstance(entry, FaqEntry) for entry in FAQ_ENTRIES)
    with pytest.raises(Exception):
        # Frozen dataclass: FAQ copy is edited in a commit, not at runtime.
        FAQ_ENTRIES[0].answer = "something else"  # type: ignore[misc]


def test_the_faq_is_design_md_s_ten_entries_verbatim_and_in_order() -> None:
    """CHAT-12 as T-CHAT-0b revised it: exactly these ten, and nothing else.

    Order is asserted alongside content because the entries are inlined into
    the prompt as written — "don't paraphrase or reorder" is one instruction,
    and only half of it would be caught by a set comparison.
    """
    expected = _entries_from_design_md()

    assert len(expected) == 10, "design.md §7 should define ten entries"
    assert [(e.question, e.answer) for e in FAQ_ENTRIES] == expected


def test_every_entry_has_a_question_and_an_answer() -> None:
    for entry in FAQ_ENTRIES:
        assert entry.question.strip()
        assert entry.answer.strip()


def test_every_entry_reaches_the_model_every_time() -> None:
    """The whole of decision 4: inlined, unconditionally.

    Asserted against ``build_system_prompt`` rather than only against
    ``faq_prompt_section`` — the section could be correct while the prompt
    dropped it, which is precisely what the removed branch used to do.
    """
    prompt = build_system_prompt()

    for entry in FAQ_ENTRIES:
        assert entry.question in prompt
        assert entry.answer in prompt


def test_the_prompt_has_one_shape() -> None:
    """No branch left to take: same string, and it contains the FAQ section."""
    assert build_system_prompt() == build_system_prompt()
    assert faq_prompt_section() in build_system_prompt()
