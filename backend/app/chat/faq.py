"""The FAQ, as a version-controlled module rather than a table (CHAT-12).

Not a database table, and that is a requirement rather than a shortcut: FAQ
copy is reviewed, diffed and rolled back like any other text in the repo, and
it has no per-row lifecycle a table would be managing. A ``faqs`` table would
also make the answers editable in an environment where nobody reviews them —
which, for text the assistant repeats verbatim to users, is the wrong
direction.

**How the FAQ reaches the model depends on its size** (design.md §7, open
decision 4). Below ``INLINE_LIMIT`` entries it is inlined into the system
prompt, which costs those tokens on every message but answers FAQ questions
with no extra round trip. Past it, inlining stops paying and the ``search_faq``
tool takes over. ``search_faq_is_enabled()`` derives that from the list's
actual length rather than from a flag someone has to remember to flip, so the
switchover happens when the condition the decision names is true rather than
when someone notices it is.
"""

from __future__ import annotations

from dataclasses import dataclass

# design.md §7 puts the switchover at "roughly 15-20 entries". 15 is the low
# end of that range: the cost of inlining is paid on every single message,
# while the cost of being wrong in the other direction is one extra round trip
# on FAQ questions only.
INLINE_LIMIT = 15

# Tokens too common to distinguish one entry from another. Kept tiny on
# purpose — this is a keyword match over a handful of hand-written entries, not
# a search engine, and every word removed here is a word a user cannot match
# on.
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
        "for", "from", "get", "how", "i", "in", "is", "it", "me", "my", "of",
        "on", "or", "the", "to", "what", "when", "where", "who", "why", "with",
    }
)


@dataclass(frozen=True)
class FaqEntry:
    """One question and its answer. Frozen — this is configuration, not state."""

    question: str
    answer: str


FAQ_ENTRIES: tuple[FaqEntry, ...] = (
    FaqEntry(
        question="How do I file a service request?",
        answer=(
            "Use the New request button in the portal, or just describe the "
            "problem here and the assistant will file it for you. A request "
            "needs a short title, a description of what is wrong, and a "
            "priority of low, medium or high."
        ),
    ),
    FaqEntry(
        question="What do the request statuses mean?",
        answer=(
            "Open means the request has been received and is waiting to be "
            "picked up. In progress means someone is working on it. Resolved "
            "means the work is done. Closed means the request is finished and "
            "no further action is expected."
        ),
    ),
    FaqEntry(
        question="How do I choose a priority?",
        answer=(
            "High is for work that is blocked right now with no workaround. "
            "Medium is for something broken that you can work around. Low is "
            "for requests that are not urgent, such as an improvement or a "
            "question."
        ),
    ),
    FaqEntry(
        question="How do I check the status of a request I filed?",
        answer=(
            "Open the request from your dashboard, or ask here with the "
            "request id and the assistant will look it up. You can only see "
            "requests you filed; administrators can see all of them."
        ),
    ),
    FaqEntry(
        question="Who can see my service requests?",
        answer=(
            "You and the portal administrators. Other users cannot see your "
            "requests, and comments marked internal are visible to "
            "administrators only."
        ),
    ),
    FaqEntry(
        question="Can I change or delete a request after filing it?",
        answer=(
            "Not yet. Requests cannot be edited or deleted from the portal at "
            "the moment. Add a comment on the request with the correction and "
            "an administrator will pick it up."
        ),
    ),
    FaqEntry(
        question="My computer will not turn on. What should I try first?",
        answer=(
            "Check that the power cable is seated at both ends and that the "
            "outlet works. On a laptop, hold the power button for ten seconds, "
            "release, then press it once. If there is still no light and no "
            "fan noise, file a high priority request describing what you "
            "tried."
        ),
    ),
    FaqEntry(
        question="I cannot connect to the wifi or the VPN. What should I try?",
        answer=(
            "Turn wifi off and on again, then forget the network and rejoin "
            "it. For the VPN, sign out fully and sign back in, and check the "
            "clock on your machine is correct. If it still fails, file a "
            "request and include any error message word for word."
        ),
    ),
    FaqEntry(
        question="I forgot my password. How do I reset it?",
        answer=(
            "Use the forgotten password link on the sign-in page if your "
            "organisation has one enabled. Otherwise file a request and an "
            "administrator will reset it. Never share your password with "
            "anyone, including this assistant."
        ),
    ),
    FaqEntry(
        question="How long will my request take?",
        answer=(
            "There is no committed response time in the portal today. High "
            "priority requests are picked up first. You can check progress at "
            "any time from your dashboard or by asking here."
        ),
    ),
)


def search_faq(query: str, *, limit: int = 3) -> list[dict[str, str]]:
    """The entries best matching ``query``, best first.

    A keyword overlap count, not a ranking model: every word of the query that
    survives ``_STOPWORDS`` and appears in an entry scores one, and entries
    scoring zero are dropped rather than padded in. With a list this small that
    is both sufficient and — the reason it is written this way — entirely
    deterministic, so the ``search_faq`` tool can be asserted against exact
    output like everything else in the suite.

    Returns plain dicts because the caller serialises the result into a
    ``tool_result`` block; a dataclass would only be converted there instead.
    """
    terms = {
        term
        for term in "".join(
            char if char.isalnum() else " " for char in query.lower()
        ).split()
        if term not in _STOPWORDS
    }
    if not terms:
        return []

    scored: list[tuple[int, int, FaqEntry]] = []
    for index, entry in enumerate(FAQ_ENTRIES):
        haystack = f"{entry.question} {entry.answer}".lower()
        score = sum(1 for term in terms if term in haystack)
        if score:
            # `index` rides along as a tiebreaker so equally scoring entries
            # come back in the order they are written above, rather than in
            # whatever order the sort happens to leave them.
            scored.append((score, index, entry))

    scored.sort(key=lambda row: (-row[0], row[1]))
    return [
        {"question": entry.question, "answer": entry.answer}
        for _, _, entry in scored[:limit]
    ]


def search_faq_is_enabled() -> bool:
    """Whether the ``search_faq`` tool is offered to the model (decision 4).

    Derived from the FAQ's length rather than hand-set, so design.md §7's rule —
    inline while it is small, switch to the tool once it is not — is enforced by
    the condition itself. Adding the sixteenth entry turns the tool on and takes
    the FAQ out of the system prompt in the same commit that adds the entry.

    The tool's *implementation* is not gated by this. ``search_faq`` executes
    whether or not it was offered, so a model that calls it anyway gets an
    answer rather than an error, and the function stays directly testable.
    """
    return len(FAQ_ENTRIES) > INLINE_LIMIT


def faq_prompt_section() -> str:
    """The FAQ as system-prompt text, or an empty string once it is too long."""
    if search_faq_is_enabled():
        return ""
    return "\n\n".join(
        f"Q: {entry.question}\nA: {entry.answer}" for entry in FAQ_ENTRIES
    )
