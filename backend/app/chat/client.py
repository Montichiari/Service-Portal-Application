"""The seam between this feature and the model (T-CHAT-0 / T-CHAT-1).

tasks.md splits the chat backend at exactly one line: everything up to the
Messages API call is deterministic and needs no API key, and only the call
itself is neither. This module *is* that line. It defines the shape of a model
response, the protocol a client satisfies, and the dependency the route
resolves — and deliberately contains no HTTP, no SDK import and no
``ANTHROPIC_API_KEY``.

**T-CHAT-0 therefore ships without a working client on purpose.**
``get_model_client`` raises, so ``POST /chat/messages`` answers XC-14's ``500``
envelope until T-CHAT-1 supplies an implementation and the config it needs.
That is the state the split was chosen to produce: it lets everything else —
schema, endpoints, tool execution, persistence, the whole trust boundary — be
built and tested before the key arrives. Tests override this dependency with a
stub that returns fixed payloads, which is also how they assert what the
endpoint does with a ``tool_use`` response without any model deciding to
produce one.

The protocol is narrow for the same reason. A client has one method, its
arguments are the three top-level fields of a Messages API request that this
feature varies (``system``, ``tools``, ``messages``), and its return value
carries the two things the orchestration loop reads (``stop_reason`` and the
content blocks). Everything the SDK adds beyond that — model id, token limits,
retries, streaming — belongs to the implementation in T-CHAT-1, not to the
callers here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

# `stop_reason` values this feature acts on. The Messages API defines others
# (`max_tokens`, `stop_sequence`, `pause_turn`, ...); the loop in
# `conversation.py` treats every one that is not `tool_use` as "the turn is
# over", which is the right default for an unrecognised value — worst case the
# user gets a truncated answer, where guessing the other way would call tools
# off a response that asked for none.
STOP_REASON_TOOL_USE = "tool_use"
STOP_REASON_END_TURN = "end_turn"


@dataclass(frozen=True)
class ModelResponse:
    """One Messages API response, reduced to what the loop reads.

    ``content`` is the raw content-block array, kept verbatim rather than
    parsed into typed objects: it is persisted to ``chat_messages.content`` as
    given (CHAT-10) and replayed back to the API unchanged, and any conversion
    in between is a chance to lose a block type this code does not know about.
    """

    stop_reason: str
    content: list[dict[str, Any]]


@runtime_checkable
class ChatModelClient(Protocol):
    """What ``conversation.py`` needs from a model client.

    ``runtime_checkable`` so a test double can be asserted to satisfy it
    without inheriting from anything — a structural check, matching the way the
    real client (an SDK wrapper) will satisfy it.
    """

    def create_message(
        self,
        *,
        system: str,
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> ModelResponse:
        """Send one request and return the model's response."""
        ...


class ModelClientNotConfiguredError(RuntimeError):
    """Raised while no client implementation exists (T-CHAT-0).

    A distinct class rather than a bare ``RuntimeError`` so the state is
    greppable and a later health check can name it. It is *not* an ``APIError``
    subclass: a missing client is an operator problem, and XC-14's 500 with the
    traceback in the log is the honest answer to the caller, not a tidy 4xx
    implying they could have sent something different.
    """


def get_model_client() -> ChatModelClient:
    """FastAPI dependency resolving the model client. Implemented in T-CHAT-1.

    Declared as a dependency rather than constructed inside the handler so
    tests can override it through ``app.dependency_overrides`` — the same
    mechanism ``get_db`` uses — instead of monkeypatching a module attribute
    and hoping every call site reads it.
    """
    raise ModelClientNotConfiguredError(
        "No Anthropic client is configured. The live Messages API call, the "
        "ANTHROPIC_API_KEY setting and the model id are T-CHAT-1's scope; "
        "T-CHAT-0 ships the rest of the chat feature against a stubbed client."
    )
