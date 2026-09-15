"""The live Messages API call (T-CHAT-1; specs/chatbot/design.md §2, §3).

This is the only module in the backend that imports the Anthropic SDK, and the
only one that reads ``ANTHROPIC_API_KEY``. ``client.py`` next door stays the
seam it was built as — the protocol, the response shape and the dependency —
so the rest of the feature is still exercised against stubs and still needs no
key. What arrives here is everything T-CHAT-0 deliberately left out: the SDK
object, the model id, the token ceiling, and the conversion from the SDK's
typed content blocks back to the plain dictionaries ``chat_messages.content``
stores.

**One client class, and ``base_url`` passed only when it is set.** design.md §2
says the Foundry-hosted deployment (decision 8) is wire-compatible with the
direct endpoint, so nothing here is provider-specific — and that is now
confirmed against the live resource rather than assumed: the first-party client
with nothing but a ``base_url`` authenticates with its ordinary ``x-api-key``
header and completes a full tool-calling exchange. An earlier draft of this
module branched to the SDK's ``AnthropicFoundry`` client on the theory that the
Azure gateway required its own ``api-key`` header. That theory was formed while
debugging an invalid credential, and it was wrong; both clients failed then and
both succeed now, so the branch was doing nothing but adding a provider name to
code that does not need one.

Unset ``ANTHROPIC_BASE_URL`` falls back to the SDK's own ``api.anthropic.com``
default, so replacing this deployment with a direct Console key is a deleted
line of ``.env`` and no code change at all.

**The response is flattened back to dictionaries on the way out.** The SDK
parses content into typed blocks (``TextBlock``, ``ToolUseBlock``, ...);
``ModelResponse.content`` is raw JSON, because those blocks are persisted to
JSONB and replayed to the API verbatim on the next call of the conversation.
``model_dump(mode="json")`` is the whole conversion, and it is deliberately
lossless: a block type this code has never heard of — a ``thinking`` block, or
something added to the API next quarter — round-trips through storage and back
into the next request untouched, because nothing here inspects it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from anthropic import Anthropic

from app.chat.client import (
    STOP_REASON_END_TURN,
    ModelClientNotConfiguredError,
    ModelResponse,
)
from app.config import settings

# How long one Messages API call may take before the SDK gives up, and how many
# times it may be retried. Constants rather than settings, per the boundary
# backend/CLAUDE.md draws: these follow from design.md §9's decision that the
# endpoint is synchronous, not from which environment it runs in. The widget
# holds the request open for the whole exchange, so the SDK's own 10-minute
# default is far too generous — a user watching a typing indicator has given up
# long before that — and the retry count is cut to one for the same reason,
# since the wall clock a caller waits is the timeout multiplied by the
# attempts, repeated for every round of the tool loop.
REQUEST_TIMEOUT_SECONDS = 60.0
MAX_RETRIES = 1


@dataclass(frozen=True)
class AnthropicChatClient:
    """A ``ChatModelClient`` backed by a real Messages API call.

    The SDK object is injected rather than constructed here so the conversion
    below can be tested without a key, a network or a live model: the
    interesting behaviour of this class is what it sends and what it does with
    what comes back, and neither needs Anthropic to participate.
    """

    sdk: Anthropic
    model: str
    max_tokens: int

    def create_message(
        self,
        *,
        system: str,
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> ModelResponse:
        """One request, one response, no loop — the loop is the caller's.

        ``thinking`` is not passed. On this model that leaves the API's own
        default in place rather than turning anything off, and the reason not
        to touch it is the same reason the content blocks are stored verbatim:
        whatever blocks come back are persisted and replayed unchanged, which
        is exactly what the API asks a client to do with them.
        """
        response = self.sdk.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            tools=tools,
            messages=messages,
        )
        return ModelResponse(
            # `None` is possible on the wire and means "not reported". The loop
            # reads this as "the turn is over", which is the safe direction —
            # the alternative would execute tool calls off a response that
            # never asked for any.
            stop_reason=response.stop_reason or STOP_REASON_END_TURN,
            content=[block.model_dump(mode="json") for block in response.content],
        )


def build_sdk_client() -> Anthropic:
    """The SDK object, pointed at whichever deployment is configured.

    Raises ``ModelClientNotConfiguredError`` rather than letting the SDK raise
    its own ``AnthropicError`` for a missing key: the distinction this codebase
    cares about is "nobody configured an assistant", which is an operator
    problem with its own named exception, and burying it inside a vendor error
    type would make it harder to recognise in a log and impossible to catch
    without importing the vendor.
    """
    if not settings.ANTHROPIC_API_KEY:
        raise ModelClientNotConfiguredError(
            "ANTHROPIC_API_KEY is not set. POST /chat/messages cannot reach a "
            "model without it; every other route is unaffected."
        )

    return Anthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        # `None` rather than an empty string when unset: the SDK treats None as
        # "use the default endpoint" and an empty string as a base URL that
        # resolves to nothing. Passed explicitly in both cases because the SDK
        # would otherwise look for its own ANTHROPIC_BASE_URL *environment*
        # variable, which pydantic-settings does not populate — it reads .env
        # into `settings` and leaves os.environ alone.
        base_url=settings.ANTHROPIC_BASE_URL or None,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=MAX_RETRIES,
    )


def build_model_client() -> AnthropicChatClient:
    """The configured client, model id and token ceiling, assembled.

    The model is read from configuration and never written into the call above
    (tasks.md): which models exist is a property of the deployment, and this
    one has exactly one.
    """
    return AnthropicChatClient(
        sdk=build_sdk_client(),
        model=settings.ANTHROPIC_MODEL,
        max_tokens=settings.ANTHROPIC_MAX_TOKENS,
    )
