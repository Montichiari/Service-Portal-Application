"""The two chat endpoints and what happens behind them (T-CHAT-0).

Contract tests against the real Postgres test database and the real
``create_app()`` (backend/CLAUDE.md) — no SQLite, no hand-assembled app. The one
thing that is *not* real is the model: ``get_model_client`` is overridden with
``StubModelClient``, which returns fixed payloads as though the model had
already decided to call a tool. design.md §11 asks for exactly that split.
Asserting on a real model's phrasing would be asserting on a coin flip; what is
deterministic here — does the endpoint validate, execute against the
authenticated user, and persist in order — is asserted exactly as hard as
everything else in this suite.

Four of these are written to fail for a specific reason rather than to describe
a feature:

* ``test_a_spoofed_identity_argument_is_ignored`` is CHAT-7 against a payload
  built the way a prompt-injected model would build one. It fails the moment a
  handler reads an id out of the model's arguments.
* ``test_the_user_message_survives_a_failing_model_call`` is CHAT-3, and is the
  only test that can tell "persisted before the call" from "persisted after a
  call that happened to succeed".
* ``test_a_user_cannot_look_up_someone_elses_request`` and its admin twin are
  CHAT-9 from both sides — a scoping test with one side passing vacuously
  proves nothing, so both assert on specific ids.
* ``test_the_loop_stops_calling_a_model_that_never_stops`` is CHAT-11's
  termination, which nothing on the happy path exercises.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.routing import APIRoute, iter_route_contexts
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.chat import tools as tools_module
from app.chat.client import ModelResponse, get_model_client
from app.db.models import ChatConversation, ChatMessage, ServiceRequest

MESSAGES = "/api/v1/chat/messages"


# --- the stubbed model -------------------------------------------------------


@dataclass
class StubModelClient:
    """A ``ChatModelClient`` that replays fixed responses and records its calls.

    The recording half is not incidental: several assertions below are about
    *what the endpoint sent* — that tool results go back as a user message
    paired by ``tool_use_id``, that the loop stops calling — and none of that is
    visible in the response body.
    """

    responses: list[ModelResponse]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def create_message(
        self,
        *,
        system: str,
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> ModelResponse:
        self.calls.append({"system": system, "tools": tools, "messages": messages})
        if not self.responses:
            raise AssertionError(
                "the stub was called more times than the test set up responses "
                f"for (call {len(self.calls)})"
            )
        return self.responses.pop(0)


@dataclass
class ExplodingModelClient:
    """A client whose call fails, for CHAT-3's "before the API call" half."""

    calls: int = 0

    def create_message(self, **_: Any) -> ModelResponse:
        self.calls += 1
        raise RuntimeError("the Messages API is unreachable")


def text_response(text: str = "All done.") -> ModelResponse:
    return ModelResponse(stop_reason="end_turn", content=[{"type": "text", "text": text}])


def tool_use_response(
    name: str, arguments: dict[str, Any], *, tool_use_id: str = "toolu_1", text: str = ""
) -> ModelResponse:
    """A response that stopped to call one tool, in the API's own shape.

    A ``tool_use`` block lives inside an **assistant** message (design.md §2),
    optionally alongside text — which is the normal case, since the model
    usually says what it is about to do.
    """
    content: list[dict[str, Any]] = []
    if text:
        content.append({"type": "text", "text": text})
    content.append(
        {"type": "tool_use", "id": tool_use_id, "name": name, "input": arguments}
    )
    return ModelResponse(stop_reason="tool_use", content=content)


CREATE_ARGUMENTS = {
    "title": "Laptop will not power on",
    "description": "No lights, no fan. Tried a different outlet.",
    "priority": "high",
}


@pytest.fixture
def use_model(api_app):
    """Install a stubbed model client on the app under test.

    Through ``dependency_overrides`` — the mechanism ``get_db`` already uses —
    rather than by monkeypatching a module attribute, so the override is scoped
    to this app instance and torn down with it.
    """

    def _use(client: Any) -> Any:
        api_app.dependency_overrides[get_model_client] = lambda: client
        return client

    return _use


@pytest.fixture
def say(use_model, client_for):
    """Send one message as ``user`` with a scripted model, return the response."""

    def _say(user, responses: list[ModelResponse], message: str = "Hello?"):
        stub = use_model(StubModelClient(list(responses)))
        response = client_for(user).post(MESSAGES, json={"message": message})
        return response, stub

    return _say


@pytest.fixture
def conversation_count(db_session):
    def _count(user=None) -> int:
        stmt = select(func.count()).select_from(ChatConversation)
        if user is not None:
            stmt = stmt.where(ChatConversation.user_id == user.id)
        return db_session.execute(stmt).scalar_one()

    return _count


@pytest.fixture
def read_session(db_session):
    """A second session on the same connection, for reading rows back.

    backend/CLAUDE.md: an assertion about *persistence* made through the
    session that did the writing may be reading a pending in-memory object
    rather than a row. A second session on the same connection sees the same
    transaction — so the test's rollback still cleans up — while going to the
    database for every attribute it is asked for.
    """
    other = Session(bind=db_session.connection())
    try:
        yield other
    finally:
        other.close()


@pytest.fixture
def stored_requests(read_session):
    """Every service request in the database, read back after the call."""

    def _stored() -> list[ServiceRequest]:
        return list(read_session.execute(select(ServiceRequest)).scalars().all())

    return _stored


@pytest.fixture
def stored_messages(read_session):
    """Every chat message in the database, oldest first, read back."""

    def _stored() -> list[ChatMessage]:
        return list(
            read_session.execute(
                select(ChatMessage).order_by(
                    ChatMessage.created_at.asc(), ChatMessage.id.asc()
                )
            )
            .scalars()
            .all()
        )

    return _stored


def assert_envelope(response, status_code: int, code: str) -> dict:
    """XC-4's shape, whole — not just the status line."""
    assert response.status_code == status_code, response.text
    body = response.json()
    assert "detail" not in body, "FastAPI's default shape leaked through"
    assert set(body) == {"error"}
    error = body["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]
    return error


def block_types(message: dict[str, Any]) -> list[str]:
    return [block["type"] for block in message["content"]]


# --- XC-5: both routes are gated ---------------------------------------------


@pytest.mark.parametrize(
    ("method", "kwargs"),
    [
        ("get", {}),
        # The CSRF header is sent so XC-9's 403 cannot stand in for the 401
        # under test — this asserts the auth gate, not the middleware in front
        # of it.
        (
            "post",
            {"json": {"message": "hi"}, "headers": {"X-Requested-With": "x"}},
        ),
    ],
)
def test_requires_a_session(method, kwargs, client) -> None:
    """XC-5 for the chat routes, asserted rather than assumed.

    backend/CLAUDE.md asks for this on every new protected route. It matters
    more here than usual: the caller *is* the conversation's identity, so a
    route declared without ``get_current_user`` would not merely skip a check —
    it would have no conversation to read or write at all, and would fail in
    some other way that a reader could mistake for a bug rather than a breach.
    """
    response = getattr(client, method)(MESSAGES, **kwargs)

    assert_envelope(response, 401, "UNAUTHENTICATED")


# --- CHAT-2: no conversation id, anywhere ------------------------------------


def test_neither_route_takes_a_conversation_id(api_app) -> None:
    """CHAT-2 read off the route table, not inferred from behaviour.

    The acceptance criterion asks for the signature specifically, and the
    distinction is real: an endpoint that accepts a ``conversation_id`` and
    then ignores it passes every behavioural test in this file while still
    presenting the parameter that decision 2 exists to remove. What is asserted
    is that there is nothing to send — no path parameter, no query parameter,
    no body field.
    """
    checked = 0
    for route_context in iter_route_contexts(api_app.routes):
        route = route_context.original_route
        if not isinstance(route, APIRoute) or "/chat/" not in route.path:
            continue
        checked += 1

        assert "{" not in route.path, route.path
        assert route_context.dependant.path_params == []

        names = {param.name for param in route_context.dependant.query_params}
        for body_field in route_context.dependant.body_params:
            annotation = body_field.field_info.annotation
            names |= set(getattr(annotation, "model_fields", {}))

        assert not any("conversation" in name.lower() for name in names), names
        assert "id" not in names

    assert checked == 2, "expected exactly the two chat routes"


# --- CHAT-1: one conversation per user, created on first use -----------------


def test_a_second_message_reuses_the_first_messages_conversation(
    make_user, say, conversation_count
) -> None:
    """CHAT-1, counted rather than inferred from a second 200.

    The acceptance criterion is explicit about this: a get-or-create that
    always creates answers both calls perfectly well and is wrong. Only the row
    count says so.
    """
    user = make_user()

    first, _ = say(user, [text_response("Hello.")])
    second, _ = say(user, [text_response("Hello again.")], message="Still there?")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert conversation_count(user) == 1
    assert conversation_count() == 1


def test_two_users_get_two_conversations(make_user, say, conversation_count) -> None:
    """The other side of CHAT-1: one *per user*, not one globally.

    Non-vacuous on both sides deliberately — a get-or-create keyed on nothing
    would hand the second user the first one's thread, and the single-user test
    above cannot tell the difference.
    """
    first_user = make_user()
    second_user = make_user()

    say(first_user, [text_response()])
    say(second_user, [text_response()])

    assert conversation_count(first_user) == 1
    assert conversation_count(second_user) == 1
    assert conversation_count() == 2


# --- CHAT-3: the user's message is persisted before the call -----------------


def test_the_user_message_survives_a_failing_model_call(
    make_user, use_model, client_for, stored_messages
) -> None:
    """CHAT-3, which only a failing call can distinguish.

    On the happy path, "persisted before" and "persisted after" are
    indistinguishable — both end with the message in the table. Forcing the
    call to raise is what separates them, and it is the case that matters:
    losing what someone typed because a network call failed is precisely the
    failure this ordering exists to prevent.
    """
    user = make_user()
    model = use_model(ExplodingModelClient())

    response = client_for(user, raise_server_exceptions=False).post(
        MESSAGES, json={"message": "My VPN keeps dropping."}
    )

    # The request itself fails, and fails in the envelope rather than leaking
    # the exception's text (XC-14).
    error = assert_envelope(response, 500, "INTERNAL_ERROR")
    assert "unreachable" not in error["message"]
    assert model.calls == 1

    stored = stored_messages()
    assert [row.role for row in stored] == ["user"]
    assert stored[0].content == [{"type": "text", "text": "My VPN keeps dropping."}]


# --- CHAT-10: every block, in order ------------------------------------------


def test_a_full_exchange_is_readable_back_in_order(
    make_user, say, client_for
) -> None:
    """CHAT-10's acceptance criterion, end to end.

    Four messages for one user turn, in the Messages API's own shape: the
    user's text, the assistant's ``tool_use`` (with the sentence it said while
    calling), the ``tool_result`` — inside a **user** message, since the API has
    no tool role — and the assistant's final text. Order is asserted across the
    whole sequence rather than as "the last one is the reply", because a
    ``tool_result`` that came back before its ``tool_use`` would be a
    transcript the API itself would reject on replay.
    """
    user = make_user()

    response, _ = say(
        user,
        [
            tool_use_response(
                "create_service_request",
                CREATE_ARGUMENTS,
                text="Let me file that for you.",
            ),
            text_response("Filed it. You can track it from your dashboard."),
        ],
        message="My laptop will not power on.",
    )

    assert response.status_code == 200, response.text
    # design.md §3 step 8: the final assistant text only — no tool machinery.
    assert response.json() == {
        "reply": "Filed it. You can track it from your dashboard."
    }

    history = client_for(user).get(MESSAGES).json()
    assert history["total"] == 4
    items = history["items"]

    assert [item["role"] for item in items] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert block_types(items[0]) == ["text"]
    assert block_types(items[1]) == ["text", "tool_use"]
    assert block_types(items[2]) == ["tool_result"]
    assert block_types(items[3]) == ["text"]

    # The blocks are stored verbatim, which is what makes the conversation
    # replayable (design.md §6) — not summarised into something readable.
    assert items[1]["content"][1]["name"] == "create_service_request"
    assert items[1]["content"][1]["input"] == CREATE_ARGUMENTS
    result = items[2]["content"][0]
    assert result["tool_use_id"] == items[1]["content"][1]["id"]
    assert result["is_error"] is False


def test_the_tool_result_goes_back_to_the_model_as_a_user_message(
    make_user, say
) -> None:
    """The replay half of CHAT-10, asserted on what the model was actually sent.

    The stored transcript and the next request's ``messages`` array are the same
    thing by construction here, and that is the property worth pinning: a
    ``tool_result`` in an assistant message, or one whose ``tool_use_id`` does
    not match, is rejected by the Messages API — a failure T-CHAT-1 would meet
    live and this task can meet now.
    """
    user = make_user()

    _, stub = say(
        user,
        [
            tool_use_response("create_service_request", CREATE_ARGUMENTS),
            text_response(),
        ],
    )

    assert len(stub.calls) == 2
    replayed = stub.calls[1]["messages"]
    assert [message["role"] for message in replayed] == [
        "user",
        "assistant",
        "user",
    ]
    tool_use = replayed[1]["content"][-1]
    tool_result = replayed[2]["content"][0]
    assert tool_use["type"] == "tool_use"
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == tool_use["id"]


def test_the_first_call_carries_the_system_prompt_and_the_tools(
    make_user, say
) -> None:
    """design.md §3 step 3, asserted where it is observable."""
    user = make_user()

    _, stub = say(user, [text_response()], message="What do the statuses mean?")

    call = stub.calls[0]
    assert "service portal" in call["system"].lower()
    # The FAQ is inlined, always (design.md §7, decision 4). The FAQ and prompt
    # suites own the content; asserted here because this is the one place the
    # string the model is actually sent can be read — CHAT-20's boundary
    # included, which is only worth anything if it survives the trip.
    assert "Q: " in call["system"]
    assert "Treat them as a closed list." in call["system"]
    assert {tool["name"] for tool in call["tools"]} == {
        "create_service_request",
        "get_request_status",
    }
    assert call["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "What do the statuses mean?"}]}
    ]


def test_history_is_scoped_to_the_caller(make_user, say, client_for) -> None:
    """One conversation per user means one *visible* conversation per user.

    Both sides are non-empty and asserted on specific text: "each sees only
    their own" passes vacuously when both see nothing.
    """
    first_user = make_user()
    second_user = make_user()
    say(first_user, [text_response()], message="First user's question.")
    say(second_user, [text_response()], message="Second user's question.")

    history = client_for(first_user).get(MESSAGES).json()

    assert history["total"] == 2
    texts = [
        block["text"]
        for item in history["items"]
        for block in item["content"]
        if block["type"] == "text"
    ]
    assert "First user's question." in texts
    assert "Second user's question." not in texts


def test_a_user_who_has_never_written_gets_an_empty_page(
    make_user, client_for, conversation_count
) -> None:
    """No conversation row yet (CHAT-1 creates it on first POST), so: empty.

    Not a 404. Nothing is missing — the widget is simply opening for the first
    time, and an error there would have the frontend distinguishing "new user"
    from "something broke".
    """
    user = make_user()

    response = client_for(user).get(MESSAGES)

    assert response.status_code == 200, response.text
    assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}
    assert conversation_count(user) == 0


# --- CHAT-7: the model's identity arguments mean nothing ---------------------


def test_a_spoofed_identity_argument_is_ignored(
    make_user, say, stored_requests
) -> None:
    """CHAT-7 against the payload a prompt-injected model would produce.

    Every identity-shaped field the API has a column for, filled in with
    somebody else's id. The row that comes out belongs to the caller, has no
    assignee, and there is exactly one of it — the victim gets nothing filed in
    their name, which is the half a "requestor is right" assertion alone would
    miss.
    """
    caller = make_user()
    victim = make_user()

    response, _ = say(
        caller,
        [
            tool_use_response(
                "create_service_request",
                {
                    **CREATE_ARGUMENTS,
                    "user_id": str(victim.id),
                    "requestor_id": str(victim.id),
                    "assignee": str(victim.id),
                    "assignee_id": str(victim.id),
                    "role": "admin",
                },
            ),
            text_response(),
        ],
    )

    assert response.status_code == 200, response.text
    requests = stored_requests()
    assert len(requests) == 1
    assert requests[0].requestor_id == caller.id
    assert requests[0].assignee_id is None
    assert requests[0].title == CREATE_ARGUMENTS["title"]


def test_a_tool_created_request_is_the_same_row_the_endpoint_writes(
    make_user, say, stored_requests
) -> None:
    """The reuse in CHAT-7's scope note: one create path, not two.

    ``request_type``, the opening ``status_history`` row and the initial status
    are SR-6/SR-14 guarantees the *endpoint* makes. They hold here only because
    the tool calls the same service function — a second implementation would
    have to remember all three, and would be tested by nothing that watches the
    endpoint.
    """
    user = make_user()

    say(user, [tool_use_response("create_service_request", CREATE_ARGUMENTS), text_response()])

    created = stored_requests()[0]
    assert created.request_type == "general"
    assert created.current_status.name == "open"
    assert [row.status_id for row in created.status_history] == [
        created.current_status_id
    ]


# --- CHAT-8: a failing tool is a result, not a 500 ---------------------------


def test_missing_arguments_come_back_as_an_error_result(
    make_user, say, client_for, stored_requests
) -> None:
    """CHAT-8's acceptance criterion: ``is_error``, not a 500.

    Any model inferring or dropping a parameter is a normal event (design.md
    §2), so this is the common path rather than an edge case. The model is told
    what was missing — it can ask the user and try again — and the person typing
    sees a conversation continue rather than a crash.
    """
    user = make_user()

    response, _ = say(
        user,
        [
            # `priority` omitted, which `ServiceRequestCreate` requires.
            tool_use_response(
                "create_service_request",
                {"title": "Printer jam", "description": "Tray two."},
            ),
            text_response("What priority should I file that as?"),
        ],
    )

    assert response.status_code == 200, response.text
    assert response.json()["reply"] == "What priority should I file that as?"
    assert stored_requests() == []

    result = client_for(user).get(MESSAGES).json()["items"][2]["content"][0]
    assert result["is_error"] is True
    assert "priority" in result["content"]
    # Only `loc` and `msg` are rendered — never the rejected input, which is
    # persisted and replayed for the life of the conversation.
    assert "Printer jam" not in result["content"]


def test_an_unknown_tool_name_comes_back_as_an_error_result(
    make_user, say, client_for
) -> None:
    """A tool the model invented. Same treatment: recoverable, not fatal."""
    user = make_user()

    response, _ = say(
        user,
        [
            tool_use_response("delete_everything", {"confirm": True}),
            text_response("I cannot do that, but I can file a request."),
        ],
    )

    assert response.status_code == 200, response.text
    result = client_for(user).get(MESSAGES).json()["items"][2]["content"][0]
    assert result["is_error"] is True
    assert "delete_everything" in result["content"]


def test_an_unexpected_tool_failure_does_not_leak_or_abort(
    make_user, say, client_for, monkeypatch
) -> None:
    """The catch-all branch: a bug inside a tool, not a bad argument.

    Two things are asserted because two things are at stake. The conversation
    survives — the user's message and the model's turn are already persisted,
    and taking the request down would lose the reply they are waiting for. And
    the exception's own text stays server-side: this string is handed to a model
    that will read it out loud, which makes it a leak with an audience.
    """
    user = make_user()

    def _boom(*_args, **_kwargs):
        raise RuntimeError("connection to postgres://portal:secret@db failed")

    monkeypatch.setitem(tools_module._HANDLERS, "get_request_status", _boom)

    response, _ = say(
        user,
        [
            tool_use_response("get_request_status", {"request_id": str(uuid.uuid4())}),
            text_response("Something went wrong looking that up."),
        ],
    )

    assert response.status_code == 200, response.text
    result = client_for(user).get(MESSAGES).json()["items"][2]["content"][0]
    assert result["is_error"] is True
    assert "postgres" not in result["content"]
    assert "secret" not in result["content"]


# --- CHAT-9: the status lookup has the endpoint's scope ----------------------


def test_a_user_cannot_look_up_someone_elses_request(
    make_user, make_service_request, say, client_for
) -> None:
    """CHAT-9, the refusal half.

    The message is the same one a malformed or missing id produces — XC-7 makes
    those three indistinguishable over HTTP, and an assistant that said "that
    request exists but is not yours" would undo it in the one channel designed
    to be talkative.
    """
    owner = make_user()
    stranger = make_user()
    request = make_service_request(owner, title="Owner's private request")

    response, _ = say(
        stranger,
        [
            tool_use_response("get_request_status", {"request_id": str(request.id)}),
            text_response("I could not find that request."),
        ],
    )

    assert response.status_code == 200, response.text
    result = client_for(stranger).get(MESSAGES).json()["items"][2]["content"][0]
    assert result["is_error"] is True
    assert "Owner's private request" not in result["content"]
    assert str(request.id) not in result["content"]


def test_an_admin_can_look_up_the_same_request(
    make_user, make_service_request, say, client_for
) -> None:
    """CHAT-9, the permission half — the *same* request the previous test hid.

    Deliberately the same fixture shape, because a scoping pair where one side
    is vacuous proves nothing: if the lookup were broken for everyone, the
    refusal test above would still pass.
    """
    owner = make_user()
    admin = make_user(role="admin")
    request = make_service_request(owner, title="Owner's private request")

    response, _ = say(
        admin,
        [
            tool_use_response("get_request_status", {"request_id": str(request.id)}),
            text_response("It is open."),
        ],
    )

    assert response.status_code == 200, response.text
    result = client_for(admin).get(MESSAGES).json()["items"][2]["content"][0]
    assert result["is_error"] is False
    assert "Owner's private request" in result["content"]
    assert '"status": "open"' in result["content"]


def test_a_user_can_look_up_their_own_request(
    make_user, make_service_request, say, client_for
) -> None:
    """And the third side: the ordinary case the other two bracket."""
    owner = make_user()
    request = make_service_request(owner, title="My own request")

    say(
        owner,
        [
            tool_use_response("get_request_status", {"request_id": str(request.id)}),
            text_response("It is open."),
        ],
    )

    result = client_for(owner).get(MESSAGES).json()["items"][2]["content"][0]
    assert result["is_error"] is False
    assert "My own request" in result["content"]


def test_the_lookup_goes_through_the_shared_visibility_loader(
    make_user, make_service_request, say, monkeypatch
) -> None:
    """CHAT-9's "via the reused dependency, not a new check", mechanically.

    The behavioural pair above passes against a hand-rolled predicate that
    happens to agree with ``visibility.py`` today. This fails unless the tool
    actually calls the shared loader — which is the requirement, because the
    danger is not a copy that is wrong now but one that stops matching after
    ``SR-12``'s rule is tightened somewhere else.
    """
    owner = make_user()
    request = make_service_request(owner)
    seen: list[tuple[str, uuid.UUID]] = []
    original = tools_module.load_visible_service_request

    def _spy(db, raw_id, user, **kwargs):
        seen.append((raw_id, user.id))
        return original(db, raw_id, user, **kwargs)

    monkeypatch.setattr(tools_module, "load_visible_service_request", _spy)

    say(
        owner,
        [
            tool_use_response("get_request_status", {"request_id": str(request.id)}),
            text_response(),
        ],
    )

    assert seen == [(str(request.id), owner.id)]


def test_a_malformed_request_id_answers_exactly_like_a_missing_one(
    make_user, say, client_for
) -> None:
    """XC-7 through the assistant: the three misses are one answer.

    The id is a plain ``str`` in the tool's schema for the same reason it is a
    plain ``str`` in the path — typing it as a UUID would split "not an id"
    away from "no such row" and hand the model a different sentence for each.
    """
    user = make_user()
    answers = []

    for request_id in ("not-a-uuid", str(uuid.uuid4())):
        say(
            user,
            [
                tool_use_response("get_request_status", {"request_id": request_id}),
                text_response(),
            ],
        )
        answers.append(
            client_for(user).get(MESSAGES).json()["items"][-2]["content"][0]["content"]
        )

    assert answers[0] == answers[1]


# --- CHAT-14: the length ceiling ---------------------------------------------


def test_an_over_long_message_is_rejected_in_the_envelope(
    make_user, use_model, client_for, stored_messages
) -> None:
    """CHAT-14: a 422, not a 500 and not a silent truncation.

    4001 is written out rather than computed from ``MAX_MESSAGE_CHARS``:
    deriving the expectation from the constant under test makes the assertion
    self-consistent instead of correct, and raising the limit would leave this
    green (backend/CLAUDE.md, found in T-AUTH-3).
    """
    user = make_user()
    model = use_model(StubModelClient([text_response()]))

    response = client_for(user).post(MESSAGES, json={"message": "x" * 4001})

    error = assert_envelope(response, 422, "VALIDATION_ERROR")
    assert "message" in error["fields"]
    # Rejected before anything was spent or written: no model call, and no
    # truncated copy of the message sitting in the table.
    assert model.calls == []
    assert stored_messages() == []


def test_a_message_at_the_limit_is_accepted(make_user, say, client_for) -> None:
    """The boundary from the other side, so the ceiling is 4000 and not 3999."""
    user = make_user()

    response, _ = say(user, [text_response()], message="y" * 4000)

    assert response.status_code == 200, response.text
    stored = client_for(user).get(MESSAGES).json()["items"][0]["content"][0]["text"]
    assert len(stored) == 4000


def test_an_empty_message_is_rejected(make_user, use_model, client_for) -> None:
    """Nothing to answer, and a real API call would be spent finding that out."""
    user = make_user()
    use_model(StubModelClient([text_response()]))

    response = client_for(user).post(MESSAGES, json={"message": ""})

    error = assert_envelope(response, 422, "VALIDATION_ERROR")
    assert "message" in error["fields"]


# --- CHAT-11: the loop terminates --------------------------------------------


def test_the_loop_stops_calling_a_model_that_never_stops(
    make_user, use_model, client_for
) -> None:
    """CHAT-11 says "repeat until end_turn", which alone is unbounded.

    Nothing on the happy path exercises this, and the failure it guards against
    is expensive in two directions at once: a held-open request the user is
    watching, and a metered API call per round. Six calls is the literal
    ceiling (``MAX_TOOL_ROUNDS`` plus the first call), written out rather than
    imported so that raising the constant does not quietly keep this green.
    """
    user = make_user()
    stub = use_model(
        StubModelClient(
            [
                tool_use_response(
                    "get_request_status",
                    {"request_id": "not-a-real-id"},
                    tool_use_id=f"toolu_{index}",
                )
                for index in range(20)
            ]
        )
    )

    response = client_for(user).post(MESSAGES, json={"message": "Go in circles."})

    assert response.status_code == 200, response.text
    assert len(stub.calls) == 6
    assert response.json()["reply"]


def test_a_tool_use_stop_reason_with_no_tool_block_ends_the_turn(
    make_user, use_model, client_for
) -> None:
    """A malformed response ends the turn instead of looping on nothing.

    Calling again would replay an identical history and stop the same way, so
    the only thing another round could add is another bill.
    """
    user = make_user()
    stub = use_model(
        StubModelClient(
            [
                ModelResponse(
                    stop_reason="tool_use",
                    content=[{"type": "text", "text": "I meant to call a tool."}],
                )
            ]
        )
    )

    response = client_for(user).post(MESSAGES, json={"message": "Hello?"})

    assert response.status_code == 200, response.text
    assert response.json() == {"reply": "I meant to call a tool."}
    assert len(stub.calls) == 1


def test_an_unrecognised_stop_reason_ends_the_turn(
    make_user, use_model, client_for
) -> None:
    """``max_tokens``, ``pause_turn``, anything new: the turn is over.

    The safe direction. Treating an unknown reason as "keep going" would run
    tool calls off a response that asked for none.
    """
    user = make_user()
    stub = use_model(
        StubModelClient(
            [
                ModelResponse(
                    stop_reason="max_tokens",
                    content=[{"type": "text", "text": "As I was saying"}],
                )
            ]
        )
    )

    response = client_for(user).post(MESSAGES, json={"message": "Tell me everything."})

    assert response.json() == {"reply": "As I was saying"}
    assert len(stub.calls) == 1


# --- CHAT-4: the replayed history is capped ----------------------------------


def test_only_the_last_twenty_messages_are_replayed(make_user, say) -> None:
    """CHAT-4 where it is observable: what the endpoint actually sent.

    Twelve turns is twenty-three stored messages by the last call, so the cap
    has to bite — a conversation short enough to fit would pass this with no
    cap implemented at all. The window's shape is asserted too, not just its
    length: it has to open on a message the API would accept as the first one
    it sees.

    ``history_window``'s own suite (``tests/chat/test_history_window.py``)
    covers the boundary cases; this is the wiring — that ``run_exchange`` calls
    it, rather than handing the model everything it has stored.
    """
    user = make_user()

    for turn in range(12):
        _, stub = say(
            user, [text_response(f"Answer {turn}.")], message=f"Question {turn}?"
        )

    sent = stub.calls[0]["messages"]
    texts = [message["content"][0]["text"] for message in sent]

    # Nineteen, not twenty: the twentieth-from-last message is an assistant
    # turn, and the window opens at the newest point that is both inside the
    # cap and a legal first message. "At most twenty" is the requirement; the
    # exact figure is a property of where the turn boundaries fall.
    assert 0 < len(sent) <= 20
    assert sent[0]["role"] == "user"
    assert sent[0]["content"][0]["type"] == "text"
    # The oldest messages are the ones dropped, and the newest is the message
    # just posted — the only direction that makes sense for a conversation.
    assert "Question 0?" not in texts
    assert texts[-1] == "Question 11?"


# --- T-CHAT-1's seam ---------------------------------------------------------


def test_without_a_configured_key_the_endpoint_fails_in_the_envelope(
    make_user, client_for
) -> None:
    """A deployment with no assistant configured: one broken route, in XC-14's
    envelope, and nothing of the exception's text in the body.

    This was T-CHAT-0's permanent state and is now a *configuration* state,
    which is the reason it is still worth a test — an instance that never set
    ``ANTHROPIC_API_KEY`` must keep serving everything else rather than fail at
    startup. The precondition is asserted rather than assumed: it is supplied
    by the suite-wide ``_no_live_model`` fixture in ``tests/conftest.py``, and a
    reader landing here should not have to guess why no real call is made.
    """
    from app.config import settings

    assert settings.ANTHROPIC_API_KEY is None

    user = make_user()

    response = client_for(user, raise_server_exceptions=False).post(
        MESSAGES, json={"message": "Anyone there?"}
    )

    error = assert_envelope(response, 500, "INTERNAL_ERROR")
    assert "ANTHROPIC_API_KEY" not in error["message"]
