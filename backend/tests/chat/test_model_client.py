"""The live client's seam, tested without going anywhere near the wire
(T-CHAT-1).

What this file can prove is everything about the call except the answer: which
model and ceiling are sent, that the four request fields arrive unaltered, that
the SDK's typed blocks come back out as the plain JSON ``chat_messages.content``
stores, and which client class a given configuration produces. All of it is
deterministic, none of it costs anything, and none of it needs a key — the
model's actual behaviour is the evals' subject (``backend/evals/``, kept out of
this suite for exactly that reason).

The SDK object is a recording double, but the *content blocks* it returns are
the SDK's real classes. That split is deliberate: the conversion under test is
``model_dump``, so a hand-rolled block with a hand-rolled ``model_dump`` would
be testing the test.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest
from anthropic import Anthropic
from anthropic.types import TextBlock, ToolUseBlock

from app.chat import client as client_module
from app.chat.anthropic_client import (
    AnthropicChatClient,
    build_model_client,
    build_sdk_client,
)
from app.chat.client import ChatModelClient, ModelClientNotConfiguredError
from app.config import settings


# --- doubles -----------------------------------------------------------------


@dataclass
class RecordingMessages:
    """Stands in for ``sdk.messages``; records the request, replays a response."""

    response: Any
    calls: list[dict[str, Any]] = field(default_factory=list)

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response


@dataclass
class RecordingSDK:
    messages: RecordingMessages


@dataclass
class FakeResponse:
    """The two fields ``AnthropicChatClient`` reads off a Messages response."""

    stop_reason: str | None
    content: list[Any]


def text_block(text: str = "All done.") -> TextBlock:
    return TextBlock(type="text", text=text)


def tool_use_block() -> ToolUseBlock:
    return ToolUseBlock(
        type="tool_use",
        id="toolu_1",
        name="create_service_request",
        input={"title": "Laptop dead", "description": "No lights.", "priority": "high"},
    )


def make_client(response: FakeResponse) -> tuple[AnthropicChatClient, RecordingSDK]:
    sdk = RecordingSDK(messages=RecordingMessages(response=response))
    return (
        AnthropicChatClient(sdk=sdk, model="test-model", max_tokens=123),
        sdk,
    )


@pytest.fixture
def uncached_client_dependency():
    """Keep ``get_model_client``'s process-wide cache out of other tests."""
    client_module._cached_client.cache_clear()
    yield
    client_module._cached_client.cache_clear()


# --- the request -------------------------------------------------------------


def test_the_request_carries_the_configured_model_and_ceiling() -> None:
    """tasks.md: the model is read from config, never written into the call."""
    client, sdk = make_client(FakeResponse("end_turn", [text_block()]))

    client.create_message(system="be brief", tools=[], messages=[])

    call = sdk.messages.calls[0]
    assert call["model"] == "test-model"
    assert call["max_tokens"] == 123


def test_the_three_varying_fields_are_forwarded_unaltered() -> None:
    """``system``, ``tools`` and ``messages`` are the protocol's whole surface.

    Asserted by identity of content rather than "was called": a client that
    quietly rebuilt the message array — dropping a block type it did not
    recognise, say — would satisfy any call-count assertion and would break
    replay, which is the one property ``chat_messages`` exists to guarantee.
    """
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        {
            "role": "assistant",
            "content": [{"type": "some_future_block", "payload": {"a": 1}}],
        },
    ]
    tools = [{"name": "create_service_request", "input_schema": {"type": "object"}}]
    client, sdk = make_client(FakeResponse("end_turn", [text_block()]))

    client.create_message(system="the prompt", tools=tools, messages=messages)

    call = sdk.messages.calls[0]
    assert call["system"] == "the prompt"
    assert call["tools"] == tools
    assert call["messages"] == messages


def test_nothing_is_streamed_and_no_thinking_is_configured() -> None:
    """The call sends what design.md §3 names and nothing else.

    design.md §9 makes this pass synchronous, and the module's reasoning for
    leaving ``thinking`` unset is that whatever blocks come back are stored and
    replayed untouched. Both are one-line changes to make by accident, and both
    would change what reaches the database.
    """
    client, sdk = make_client(FakeResponse("end_turn", [text_block()]))

    client.create_message(system="s", tools=[], messages=[])

    assert set(sdk.messages.calls[0]) == {
        "model",
        "max_tokens",
        "system",
        "tools",
        "messages",
    }


# --- the response ------------------------------------------------------------


def test_typed_blocks_come_back_as_plain_json() -> None:
    """The conversion that makes a response storable and replayable.

    ``chat_messages.content`` is JSONB and the array is sent back to the API on
    the next call, so an SDK object surviving this boundary is a write that
    fails at commit — or, worse, a response that serialises today and stops
    when the SDK changes a field.
    """
    client, _ = make_client(
        FakeResponse("tool_use", [text_block("Filing that."), tool_use_block()])
    )

    response = client.create_message(system="s", tools=[], messages=[])

    assert all(isinstance(block, dict) for block in response.content)
    # Round-trips through JSON unchanged — the actual requirement, where
    # "is a dict" is only its symptom.
    assert json.loads(json.dumps(response.content)) == response.content
    assert response.content[0] == {"type": "text", "text": "Filing that.", "citations": None}
    tool_call = response.content[1]
    assert tool_call["type"] == "tool_use"
    assert tool_call["name"] == "create_service_request"
    assert tool_call["input"]["priority"] == "high"


def test_the_stop_reason_is_passed_through() -> None:
    """``tool_use`` is the one value the loop branches on."""
    client, _ = make_client(FakeResponse("tool_use", [tool_use_block()]))

    assert client.create_message(system="s", tools=[], messages=[]).stop_reason == (
        "tool_use"
    )


def test_an_absent_stop_reason_ends_the_turn() -> None:
    """``None`` is possible on the wire, and must not read as ``tool_use``.

    The loop executes tool calls on ``tool_use`` and stops on everything else,
    so the safe mapping is the one that stops: a missing reason produces a
    short answer rather than tool calls made off a response that requested
    none.
    """
    client, _ = make_client(FakeResponse(None, [text_block()]))

    assert client.create_message(system="s", tools=[], messages=[]).stop_reason == (
        "end_turn"
    )


def test_it_satisfies_the_protocol_the_loop_depends_on() -> None:
    """Structural, like the stub in ``tests/api/test_chat.py`` is.

    ``run_exchange`` is typed against ``ChatModelClient`` and Python does not
    check that at runtime, so nothing else in the suite would notice a renamed
    parameter until a live call failed.
    """
    client, _ = make_client(FakeResponse("end_turn", []))

    assert isinstance(client, ChatModelClient)


# --- construction ------------------------------------------------------------


def test_without_a_key_the_client_refuses_to_be_built(monkeypatch) -> None:
    """The T-CHAT-0 state, still reachable: no key, no assistant, no crash.

    The named exception matters more than the raise. ``POST /chat/messages``
    turns this into XC-14's 500 and every other route keeps working, which is
    the correct behaviour for a deployment that simply has no model configured
    — and an operator reading the log needs to see that, not a vendor error
    about a missing argument.
    """
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)

    with pytest.raises(ModelClientNotConfiguredError):
        build_sdk_client()


def test_a_configured_base_url_is_where_the_client_points(monkeypatch) -> None:
    """design.md decision 8: the deployment is a config value, not a code path.

    Asserted on the constructed client rather than on a class name. The Foundry
    resource is wire-compatible — verified live, see
    ``app/chat/anthropic_client.py`` — so there is nothing provider-specific to
    pin here beyond the endpoint actually being used.
    """
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "a-key")
    monkeypatch.setattr(
        settings, "ANTHROPIC_BASE_URL", "https://example.services.ai.azure.com/anthropic"
    )

    sdk = build_sdk_client()

    assert isinstance(sdk, Anthropic)
    assert "example.services.ai.azure.com" in str(sdk.base_url)


def test_no_base_url_falls_back_to_the_first_party_endpoint(monkeypatch) -> None:
    """The other half of decision 8: a Console key, and no code change.

    tasks.md asks for this explicitly — the base URL is passed only when set,
    so replacing the Foundry resource with a direct key is a deleted line of
    ``.env``. The empty-string case is covered too, because a half-deleted
    ``.env`` line is the realistic way to arrive at "unset": an empty string
    reaching the SDK would be a base URL pointing nowhere rather than a
    fallback to the default.
    """
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "a-key")

    for unset in (None, ""):
        monkeypatch.setattr(settings, "ANTHROPIC_BASE_URL", unset)

        sdk = build_sdk_client()

        assert isinstance(sdk, Anthropic)
        assert "api.anthropic.com" in str(sdk.base_url)


def test_the_model_and_ceiling_come_from_settings(monkeypatch) -> None:
    """Changing configuration changes the request — not a second constant."""
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "a-key")
    monkeypatch.setattr(settings, "ANTHROPIC_BASE_URL", None)
    monkeypatch.setattr(settings, "ANTHROPIC_MODEL", "some-other-model")
    monkeypatch.setattr(settings, "ANTHROPIC_MAX_TOKENS", 77)

    client = build_model_client()

    assert client.model == "some-other-model"
    assert client.max_tokens == 77


def test_the_default_model_is_the_one_deployed(monkeypatch) -> None:
    """design.md decision 1 (revised), pinned to the literal it states.

    Read off a freshly constructed ``Settings`` rather than the live one, so a
    local ``.env`` overriding the model for an experiment cannot make this
    green or red for the wrong reason.
    """
    from app.config import Settings

    defaults = Settings.model_fields["ANTHROPIC_MODEL"]

    assert defaults.default == "claude-sonnet-5"


def test_the_dependency_hands_out_one_client_per_process(
    monkeypatch, uncached_client_dependency
) -> None:
    """One SDK object, one connection pool, built on first use.

    A per-request client would open a fresh TLS connection for every message on
    an endpoint the user is already waiting on. Building it lazily rather than
    at import is the other half: an unset key must fail one route, not the
    application's startup.
    """
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "a-key")
    monkeypatch.setattr(settings, "ANTHROPIC_BASE_URL", None)

    assert client_module.get_model_client() is client_module.get_model_client()
