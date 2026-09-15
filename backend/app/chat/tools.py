"""The assistant's tools: what they accept, and what happens when it calls one
(CHAT-5, CHAT-7, CHAT-8, CHAT-9; design.md §4, §5).

Three properties of this module matter more than the code in it.

**Every tool runs against the session's user, never the model's.** design.md §5
puts model output on the same footing as any other untrusted input, so no
handler below takes an identity argument. ``execute_tool`` is handed the
``User`` that ``get_current_user`` resolved, and passes that; an ``input``
object in which the model invented a ``user_id`` or an ``assignee`` reaches a
schema that has no such field and ignores unknown keys, so it changes nothing
about the row that gets written (CHAT-7).

**Every tool calls the code the equivalent endpoint calls.** Creation goes
through ``app.services.service_requests.create_service_request``; the status
lookup goes through ``app.api.visibility.load_visible_service_request``, which
is the same function ``GET /service-requests/{id}`` resolves (CHAT-9,
decision 3). Not a second predicate that agrees with it today — the same one.
A visibility rule with two implementations is the shape of bug where one of
them is tightened later and the other quietly is not, and here the copy would
be the one facing a component that can be talked into asking for anything.

**A failing tool is a result, not a failed request** (CHAT-8). Invalid
arguments and invisible rows come back as ``tool_result`` blocks with
``is_error: true``, which the model can read and recover from — by asking the
user for the missing field, typically. Raising instead would turn "the model
guessed a parameter wrong", which is a normal event with any model
(design.md §2), into a 500 for the person typing.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session, joinedload

from app.api.errors import NotFoundError
from app.api.schemas.common import as_utc_iso8601
from app.api.schemas.service_request import ServiceRequestCreate
from app.api.visibility import load_visible_service_request
from app.db.models import ServiceRequest, User
from app.services.service_requests import create_service_request

logger = logging.getLogger(__name__)

CREATE_SERVICE_REQUEST = "create_service_request"
GET_REQUEST_STATUS = "get_request_status"

# What a caller is told when a lookup finds nothing they may see. One message
# for "malformed id", "no such request" and "someone else's request" alike —
# `load_visible_service_request` raises the same `NotFoundError` for all three
# (XC-7, SR-13), and spelling the difference out here would undo through the
# assistant exactly what the HTTP layer is careful not to leak.
NOT_VISIBLE_MESSAGE = (
    "No service request with that id is visible to you. Ask the user to check "
    "the id, or offer to file a new request."
)

# The catch-all's message. Deliberately content-free, for the same reason
# XC-14's 500 envelope is: an unexpected exception's text routinely carries a
# SQL fragment or a connection string, and this one is handed to a model that
# will repeat it to the user.
UNEXPECTED_FAILURE_MESSAGE = (
    "That tool failed for an unexpected reason. Tell the user the action could "
    "not be completed and suggest they try again shortly."
)


# --- argument schemas --------------------------------------------------------
#
# `create_service_request` has none of its own: it validates through
# `ServiceRequestCreate`, the schema `POST /service-requests` already uses, so
# the tool cannot accept a request body the endpoint would reject or reject one
# it would accept. The two below exist because their endpoints' equivalents are
# path parameters, which have no schema to borrow.


class RequestStatusArguments(BaseModel):
    """``get_request_status``'s arguments."""

    # `extra="ignore"` on both models here for the reason design.md §5 gives:
    # an argument the model invented — `user_id`, `assignee`, `role` — should
    # change nothing, and dropping it silently is what "ignored" means. The
    # alternative, rejecting the whole call, would turn a harmless
    # hallucination into a failure the user sees.
    model_config = ConfigDict(extra="ignore")

    # A plain `str`, not a `UUID`. Same reasoning as the path parameter on
    # `GET /service-requests/{id}`: a malformed id must be answered exactly
    # like a missing one, and typing it as a UUID here would split those into
    # two different failure messages — one of which ("that isn't a valid id")
    # tells the model, and through it the user, something about ids rather than
    # about their request.
    request_id: str = Field(min_length=1)


# --- tool definitions (CHAT-5) -----------------------------------------------


def _input_schema(
    model: type[BaseModel], descriptions: Mapping[str, str]
) -> dict[str, Any]:
    """A Pydantic model's JSON Schema, as an Anthropic ``input_schema``.

    Derived rather than hand-written, which is the whole point: a hand-written
    copy of ``ServiceRequestCreate``'s fields would keep validating against
    itself while drifting from the schema that actually decides whether the
    create succeeds. The failure that produces is quiet and one-sided — the
    model omits a field it was never told about, every create comes back
    ``is_error``, and nothing in the API's own tests is any different.

    Only the per-field ``description`` values are added on top, because they
    are the one thing the model needs and the HTTP schema has no use for:
    putting them on ``ServiceRequestCreate`` itself would write prompt copy
    into the published OpenAPI document.
    """
    schema = model.model_json_schema()
    # Pydantic names the schema after the class and copies the docstring in.
    # Neither says anything useful to the model — the tool's own `description`
    # covers that — and the class name in particular describes an HTTP body.
    schema.pop("title", None)
    schema.pop("description", None)
    for field, text in descriptions.items():
        schema["properties"][field]["description"] = text
    return schema


TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    CREATE_SERVICE_REQUEST: {
        "name": CREATE_SERVICE_REQUEST,
        "description": (
            "File a new service request for the user you are talking to. Use "
            "this once you know what is wrong and can write a short title and "
            "a description in the user's own words. The request is always "
            "filed for the signed-in user; you cannot file one for anybody "
            "else. Returns the new request's id and status."
        ),
        "input_schema": _input_schema(
            ServiceRequestCreate,
            {
                "title": (
                    "A short summary of the problem, as it would appear in a "
                    "ticket list. At most 200 characters."
                ),
                "description": (
                    "What is wrong, in detail: what the user was doing, what "
                    "happened, any error message word for word, and anything "
                    "they have already tried."
                ),
                "priority": (
                    "high when the user is blocked with no workaround, medium "
                    "when something is broken but workable, low for requests "
                    "that are not urgent. Judge it from what the user "
                    "describes; ask them if it is genuinely unclear."
                ),
            },
        ),
    },
    GET_REQUEST_STATUS: {
        "name": GET_REQUEST_STATUS,
        "description": (
            "Look up one service request by id and return its current status, "
            "title, priority and timestamps. Only requests the signed-in user "
            "is allowed to see can be looked up; administrators may look up "
            "any request. If the user does not have the id to hand, ask them "
            "for it."
        ),
        "input_schema": _input_schema(
            RequestStatusArguments,
            {
                "request_id": (
                    "The service request's id, as shown in the portal. A UUID "
                    "such as 3f4b2c1e-9d7a-4a58-8f2e-1c0b7d5a6e34."
                )
            },
        ),
    },
}


def available_tools() -> list[dict[str, Any]]:
    """The tool definitions to send with a request, in a stable order.

    Both tools, every request. Membership used to move — a third, FAQ-search
    tool joined the list once the FAQ outgrew the system prompt — and
    T-CHAT-0b removed that tool and the threshold together, so this is now a
    fixed list read off a fixed table. FAQ answers reach the model in the
    ``system`` prompt instead (design.md §7, decision 4).

    Still a function rather than a module-level list: callers get their own
    list to hand to the SDK, and nothing upstream can mutate the shared one.
    """
    return [
        TOOL_DEFINITIONS[name]
        for name in (CREATE_SERVICE_REQUEST, GET_REQUEST_STATUS)
    ]


# --- execution ---------------------------------------------------------------


def _result_block(tool_use_id: str, payload: Any) -> dict[str, Any]:
    """A successful ``tool_result``.

    ``content`` is a JSON string rather than a bare sentence: the model reads
    field names back to the user (a status, an id it will need again) and JSON
    keeps those unambiguous. ``is_error`` is written explicitly on the success
    path too, so both shapes carry the same keys and a reader of a stored
    conversation never has to infer the flag's absence.
    """
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(payload),
        "is_error": False,
    }


def _error_block(tool_use_id: str, message: str) -> dict[str, Any]:
    """A failed ``tool_result`` (CHAT-8). Plain text: it is meant to be read."""
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": message,
        "is_error": True,
    }


def _argument_error_message(exc: ValidationError) -> str:
    """Turn a ``ValidationError`` into something the model can act on.

    Only ``loc`` and ``msg`` are read — never ``input`` and never ``ctx``. That
    is the same rule ``validation_error_fields`` follows in ``app/api/errors.py``
    and it is not theoretical here either: this text is persisted to
    ``chat_messages`` and sent back to the model, so an echoed input value is a
    rejected value stored and transmitted for as long as the conversation
    lives.
    """
    problems = "; ".join(
        f"{'.'.join(str(part) for part in error.get('loc', ())) or 'arguments'}: "
        f"{error.get('msg', 'invalid')}"
        for error in exc.errors()
    )
    return (
        f"Those arguments were rejected — {problems}. Ask the user for what is "
        "missing, then call the tool again."
    )


def _run_create_service_request(
    arguments: Mapping[str, Any], *, db: Session, user: User
) -> dict[str, Any]:
    """CHAT-7: filed for ``user``, whatever the arguments claim."""
    payload = ServiceRequestCreate.model_validate(arguments)
    created = create_service_request(db, requestor=user, payload=payload)
    return {
        "request_id": str(created.id),
        "title": created.title,
        "priority": created.priority,
        "status": created.current_status.name,
        "created_at": as_utc_iso8601(created.created_at),
    }


def _run_get_request_status(
    arguments: Mapping[str, Any], *, db: Session, user: User
) -> dict[str, Any]:
    """CHAT-9: the same scope ``GET /service-requests/{id}`` applies.

    ``load_visible_service_request`` raises ``NotFoundError`` for a malformed
    id, a missing row and someone else's row alike; ``execute_tool`` renders
    all three as the one ``NOT_VISIBLE_MESSAGE``. An admin reaches any row
    through the same call because ``service_request_conditions`` adds no
    predicate for them — there is no branch here that could disagree with the
    endpoint's.
    """
    args = RequestStatusArguments.model_validate(arguments)
    request = load_visible_service_request(
        db,
        args.request_id,
        user,
        # One row, but the status is read below and a lazy load after the
        # fetch is a second round trip for a value the first could have
        # carried. The other two embedded relationships are not read here, so
        # they are not joined.
        options=(joinedload(ServiceRequest.current_status),),
    )
    return {
        "request_id": str(request.id),
        "title": request.title,
        "status": request.current_status.name,
        "priority": request.priority,
        "created_at": as_utc_iso8601(request.created_at),
        "updated_at": as_utc_iso8601(request.updated_at),
    }


_HANDLERS: dict[str, Callable[..., Any]] = {
    CREATE_SERVICE_REQUEST: _run_create_service_request,
    GET_REQUEST_STATUS: _run_get_request_status,
}


def execute_tool(
    block: Mapping[str, Any], *, db: Session, user: User
) -> dict[str, Any]:
    """Run one ``tool_use`` block and return its ``tool_result`` block.

    ``user`` is the authenticated caller and is the *only* identity any handler
    sees (CHAT-7). ``block`` is the model's, and nothing in it is trusted
    further than the dispatch below: an unknown ``name``, a missing ``input``,
    and arguments of the wrong shape are all ordinary outcomes here rather than
    exceptions.

    A name this module does not implement — a tool from an older prompt, a
    hallucinated one — is an ``is_error`` result naming the tools that do
    exist, not an exception. The model can read that and call the right one.
    """
    tool_use_id = str(block.get("id", ""))
    name = block.get("name")
    raw_arguments = block.get("input")
    arguments = raw_arguments if isinstance(raw_arguments, Mapping) else {}

    handler = _HANDLERS.get(str(name))
    if handler is None:
        return _error_block(
            tool_use_id,
            f"There is no tool named {name!r}. Use one of: "
            f"{', '.join(sorted(_HANDLERS))}.",
        )

    try:
        payload = handler(arguments, db=db, user=user)
    except ValidationError as exc:
        # CHAT-8's named case: the model left out a required field or sent the
        # wrong type. Recoverable by the model, so it is told what was wrong.
        return _error_block(tool_use_id, _argument_error_message(exc))
    except NotFoundError:
        # CHAT-8's other named case, and CHAT-9's refusal path — which is the
        # same path, deliberately: "you may not see that" and "there is no
        # such row" are one answer here exactly as they are one answer over
        # HTTP.
        return _error_block(tool_use_id, NOT_VISIBLE_MESSAGE)
    except Exception:
        # Everything else is a bug rather than a bad argument, and it is caught
        # for one reason: an exception escaping here aborts a request the user
        # is watching, after their message has already been persisted and
        # possibly after another tool in the same turn has already written a
        # row. The traceback still reaches the log exactly as XC-14's 500 path
        # would log it; only the client-facing half differs.
        logger.exception("Chat tool %r failed for user %s", name, user.id)
        # The session may be in a failed transaction — a flush that raised
        # leaves it unusable — and the caller has messages still to persist
        # after this returns. Rolling back here is what keeps a broken tool
        # from taking the conversation's own writes down with it.
        db.rollback()
        return _error_block(tool_use_id, UNEXPECTED_FAILURE_MESSAGE)

    return _result_block(tool_use_id, payload)
