"""The FAQ, as a version-controlled module rather than a table (CHAT-12).

Not a database table, and that is a requirement rather than a shortcut: FAQ
copy is reviewed, diffed and rolled back like any other text in the repo, and
it has no per-row lifecycle a table would be managing. A ``faqs`` table would
also make the answers editable in an environment where nobody reviews them --
which, for text the assistant repeats verbatim to users, is the wrong
direction.

**The ten entries below are always inlined into the system prompt**
(design.md §7, decision 4). There is no size threshold and no FAQ-search tool:
both existed while decision 4 was open, and both were removed in ``T-CHAT-0b``
once it closed in favour of a fixed, hand-maintained set. This is not a
scaled-down version of a bigger mechanism — it is the answer for a FAQ that
changes when a person edits it. If the list ever genuinely outgrows a
system prompt, that is a human-noticed event that gets its own task and its own
justification, not a threshold running quietly in the background for a
condition that may never be met.

The entries are copied verbatim from design.md §7, in its order.
``app/chat/prompt.py`` states the grounding boundary that goes with them
(CHAT-20): these ten are the whole of what the assistant knows, and a question
outside them is one to decline rather than improvise on.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FaqEntry:
    """One question and its answer. Frozen — this is configuration, not state."""

    question: str
    answer: str


FAQ_ENTRIES: tuple[FaqEntry, ...] = (
    FaqEntry(
        question="How do I reset my password?",
        answer=(
            "Use the \"Forgot password\" link on the sign-in page to reset it "
            "yourself. If you don't have access to your recovery email, "
            "submit a ticket and IT will reset it manually — this usually "
            "takes under an hour during business hours."
        ),
    ),
    FaqEntry(
        question="My VPN won't connect. What should I try first?",
        answer=(
            "Restart the VPN client, confirm you're on a working internet "
            "connection, and make sure your VPN app is on the latest "
            "version. If it still won't connect after that, submit a ticket "
            "with the error message you're seeing."
        ),
    ),
    FaqEntry(
        question="How do I request new software be installed on my computer?",
        answer=(
            "Submit a service request with the software name and a short "
            "reason for the request. Most standard business software is "
            "approved within a day; anything outside the approved list "
            "needs manager sign-off first."
        ),
    ),
    FaqEntry(
        question="My printer isn't working. What should I check?",
        answer=(
            "Confirm the printer is powered on and connected to the "
            "network, then try removing and re-adding it in your system's "
            "printer settings. If a specific print job is stuck, cancel and "
            "resend it. Still stuck? Submit a ticket with the printer's "
            "name or location."
        ),
    ),
    FaqEntry(
        question="How do I connect to the office Wi-Fi?",
        answer=(
            "Select the office network from your Wi-Fi settings and sign in "
            "with your usual company username and password. If it doesn't "
            "accept your credentials, your account may need to be added to "
            "the Wi-Fi group — submit a ticket and we'll sort it out."
        ),
    ),
    FaqEntry(
        question="My computer won't turn on. What should I do?",
        answer=(
            "Check the power cable and outlet, and hold the power button "
            "for about 10 seconds in case it's frozen. If there's still no "
            "response, submit a ticket marked high priority so we can get "
            "you a loaner while we look into it."
        ),
    ),
    FaqEntry(
        question="How do I submit a new IT service request?",
        answer=(
            "You can ask the assistant to create one directly — just "
            'describe the issue — or use the "Submit Request" page from '
            "the dashboard. Either way, a clear title and description "
            "helps it get picked up faster."
        ),
    ),
    FaqEntry(
        question="How can I check the status of an existing ticket?",
        answer=(
            "Ask the assistant for the status directly, or check it any "
            "time from the dashboard, where every submitted request is "
            "listed with its current status."
        ),
    ),
    FaqEntry(
        question="What's the typical response time for a support ticket?",
        answer=(
            "Most tickets get a first response within one business day. "
            "High-priority issues — like a completely inaccessible computer "
            "— are typically picked up faster; if something's urgent, say "
            "so in the description."
        ),
    ),
    FaqEntry(
        question=(
            "My email isn't syncing, or I'm not receiving new "
            "messages. What should I check?"
        ),
        answer=(
            "Check the internet connection first, then confirm the mailbox "
            "isn't near its storage limit. If neither explains it, submit a "
            "ticket — this is sometimes a sync issue on the server side."
        ),
    ),
)


def faq_prompt_section() -> str:
    """The FAQ as system-prompt text.

    Unconditional: every entry, every time. The branch that used to live here
    asked whether the list had outgrown inlining, which is the mechanism
    decision 4 removed.
    """
    return "\n\n".join(
        f"Q: {entry.question}\nA: {entry.answer}" for entry in FAQ_ENTRIES
    )
