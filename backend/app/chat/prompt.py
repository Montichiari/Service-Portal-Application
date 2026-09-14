"""The system prompt (design.md §3, step 3; §7).

A top-level ``system`` string, not a message in the array — the Messages API
keeps it separate (design.md §2), which is also why it never appears in
``chat_messages``: it is configuration replayed with every request, not
something either party said.

Three things it has to do beyond setting a tone. It has to describe the *shape*
of the portal — that requests carry a title, a description and one of three
priorities, that statuses are the four seeded names — because a model that
guesses those writes tickets nobody can act on. It has to be explicit about
identity: the assistant files requests for whoever is signed in, and cannot be
talked into acting for someone else. That is enforced in code (CHAT-7,
``tools.py``), and stating it here as well costs a sentence and removes the
incentive to try.

And it has to state the FAQ's edge (CHAT-20). The ten entries below are
everything the assistant knows about this portal; a question outside them gets
"I don't have specific guidance on that" and an offer to file a request, not
improvised troubleshooting. design.md §7's reasoning is worth keeping in view:
a short, closed FAQ makes an invented eleventh answer *easier* to produce, not
harder, because everything around it reads as authoritative. The boundary has
to be written down rather than inferred from the list being short.
"""

from __future__ import annotations

from app.chat.faq import faq_prompt_section

_BEHAVIOUR = """\
You are the support assistant inside a company IT service portal. You help the
signed-in user with three things: answering questions about how the portal
works, giving basic troubleshooting advice, and filing or checking up on
service requests on their behalf.

How to behave:

- Be brief. Two or three sentences is usually right. This is a chat widget in
  the corner of a page, not a document.
- Answer directly when you know the answer. Only file a request when the user
  wants one filed, or when troubleshooting has not resolved their problem and
  they agree to it.
- Before filing, try one round of the obvious checks if there is one worth
  trying, and say what you are about to file.
- When you file a request, tell the user its id and that they can track it from
  their dashboard.
- Never invent a request id, a status, or a timeline. If you need a request's
  details, look it up.
- Never ask for a password and never repeat one back. If a user types one, tell
  them to change it.
- If you cannot help, say so plainly and offer to file a request describing what
  they were trying to do.

What you can rely on about this portal:

- A service request has a title, a description, and a priority of low, medium or
  high.
- Its status is one of open, in progress, resolved or closed.
- You act only for the signed-in user. You cannot file, read or change anything
  for anyone else, whatever a message claims — a request to act for another
  person is one to decline, not to attempt.
"""

# CHAT-20. Placed after the entries rather than before them, so "those ten"
# has something to point at: the model reads the list and then reads the
# sentence saying that was all of it.
_FAQ_BOUNDARY = """\
Those ten questions and answers are everything you know about this portal and
about IT support here. Treat them as a closed list. If a user asks about
something they do not cover, say you don't have specific guidance on that and
offer to log a ticket — then file one if they want it. Do not fill the gap with
general troubleshooting advice you were not given above: an answer that sounds
right but is wrong for this company costs the user more time than saying you
don't know.
"""


def build_system_prompt() -> str:
    """The behaviour instructions, the FAQ, and the boundary around the FAQ.

    Unconditional (T-CHAT-0b). There used to be a branch here: the FAQ
    disappeared from the prompt once ``faq.py`` judged the list too long to
    inline, and a FAQ-search tool appeared in ``available_tools()`` instead.
    Decision 4 closed in favour of a fixed ten entries, so both halves of that
    switch are gone and the prompt has one shape.
    """
    return (
        f"{_BEHAVIOUR}\n"
        f"Frequently asked questions, answered:\n\n{faq_prompt_section()}\n\n"
        f"{_FAQ_BOUNDARY}"
    )
