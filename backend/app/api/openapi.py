"""The generated OpenAPI document, corrected to match what this API does
(T-DOCS-0).

FastAPI derives the spec from route signatures, and the three most important
facts about this API's contract are invisible to that derivation:

* **The error shape.** ``register_exception_handlers`` replaces FastAPI's
  ``{"detail": [...]}`` with design.md §1's envelope on every error path, but
  the generator has never heard of that and keeps documenting
  ``HTTPValidationError``. A client generated from the uncorrected spec parses
  ``detail`` and finds ``error`` — the spec was not merely incomplete there, it
  was wrong.
* **Authentication.** ``get_current_user`` reads a cookie off the raw
  ``Request`` rather than declaring a security dependency, so nothing about the
  session reaches the generator.
* **CSRF.** ``RequireCustomHeaderMiddleware`` runs before routing, so
  ``X-Requested-With`` appears in no route signature at all — which is exactly
  why a reader of ``/docs`` would otherwise have every write fail ``403`` with
  nothing in the spec to explain it.

So the document is post-processed here rather than annotated route by route.
``use_corrected_openapi`` wraps ``app.openapi`` once, from ``create_app()``; no
route has to opt in, and a route added later inherits every correction below
without remembering to.

**What is derived vs. what a route declares.** Anything structural is derived
from the route's own dependency tree and path — a route behind
``get_current_user`` can answer ``401``, a route with a path parameter can
answer ``404``, a route with a state-changing method can answer ``403``, and
every route can answer ``500``. None of that is repeated in a decorator, for
the same reason the CSRF check is middleware rather than a per-route
dependency: the one route that forgot would be the one that mattered. What is
*not* structural — AUTH-2's ``409``, AUTH-7's ``401``, CM-7's ``403``,
``/health``'s ``503`` — is declared at the route in ``responses=``, next to
the code that raises it, as a **cause fragment** rather than a finished
sentence (see ``_render_reasons``) so that it composes with the structural
reasons for the same status instead of overwriting them.

**``500`` is documented per operation**, not once globally: OpenAPI has no
global ``responses`` object, and a reader looking at one route is better served
seeing it there than in a preamble. That repeats a one-line entry, not a
definition — every error response in the document, on every route, points at
the single ``ErrorEnvelope`` schema component.

This module changes documentation only. It reads the app; it never alters
routing, handlers, or responses.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts

from app.api.deps import get_current_user
from app.api.errors import ErrorCode
from app.api.middleware import CSRF_HEADER, SAFE_METHODS
from app.core.security import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME

# FastAPI's default was `0.1.0`, which said nothing at all. This at least moves
# when the contract does.
SPEC_VERSION = "1.0.0"

ENVELOPE_SCHEMA_NAME = "ErrorEnvelope"
DETAIL_SCHEMA_NAME = "ErrorDetail"
ENVELOPE_REF = f"#/components/schemas/{ENVELOPE_SCHEMA_NAME}"
DETAIL_REF = f"#/components/schemas/{DETAIL_SCHEMA_NAME}"

ACCESS_COOKIE_SCHEME = "accessTokenCookie"
REFRESH_COOKIE_SCHEME = "refreshTokenCookie"

# FastAPI's stock validation components. Nothing in this API can emit either
# shape — `validation_exception_handler` intercepts every
# `RequestValidationError` before it is rendered — so they are removed rather
# than left standing beside the real one, where they would read as a second,
# equally valid error format.
_STOCK_VALIDATION_SCHEMAS = ("HTTPValidationError", "ValidationError")

_ERROR_CODES = ", ".join(f"`{code.value}`" for code in ErrorCode)

API_DESCRIPTION = f"""\
Service portal API. Every path below is mounted under `/api/v1` except the
`/health` probe, which is an operational endpoint outside the contract.

### Errors

Every error response — validation failures, auth failures, not-found and
unhandled crashes alike — uses one envelope:

```json
{{
  "error": {{
    "code": "VALIDATION_ERROR",
    "message": "One or more fields are invalid.",
    "fields": {{ "email": ["value is not a valid email address"] }}
  }}
}}
```

`fields` is present only on `VALIDATION_ERROR`, so its presence is meaningful.
`code` is a closed set: {_ERROR_CODES}.

Every operation can additionally answer `500` with an `INTERNAL_ERROR`
envelope; its `message` is deliberately content-free and the traceback stays in
the server log.

### Authentication

Sessions are cookie-based. `POST /api/v1/auth/login` sets `{ACCESS_COOKIE_NAME}`
(1 hour) and `{REFRESH_COOKIE_NAME}` (30 days), both `httpOnly`, `Secure` and
`SameSite=Lax`; the browser attaches them automatically and no client-side
script can read them. There is no `Authorization` header and no bearer token.
Operations marked with a lock require `{ACCESS_COOKIE_NAME}`;
`POST /api/v1/auth/refresh` requires `{REFRESH_COOKIE_NAME}` instead, and
rotates it.

### `{CSRF_HEADER}` is required on every write

**Every request whose method is not `GET`, `HEAD` or `OPTIONS` must carry a
`{CSRF_HEADER}` header**, with any non-empty value. It is enforced by
middleware ahead of routing, so a write that omits it is answered `403` /
`FORBIDDEN` before the route, the body, or the session cookie is looked at. It
is listed as a required header parameter on every such operation below.
"""

# --- Reason fragments --------------------------------------------------------
#
# Each is the *cause* half of a sentence `_render_reasons` completes, so that
# several reasons for one status read as one description instead of the last
# one written winning. Route-declared fragments follow the same convention.

_UNAUTHENTICATED_REASON = (
    f"the `{ACCESS_COOKIE_NAME}` cookie is absent, expired, or no longer names "
    "an active user — no distinction is drawn between those cases (XC-5)"
)
_CSRF_REASON = (
    f"the `{CSRF_HEADER}` header is missing, which middleware refuses before "
    "routing (XC-9)"
)
_ROLE_REASON = "the caller's role is below the one this operation requires (XC-6)"
_NOT_FOUND_REASON = (
    "no service request with that id is visible to the caller — a malformed id, "
    "an id matching no row, and an id belonging to someone else are answered "
    "identically by design (XC-7, SR-13)"
)
_VALIDATION_REASON = "one or more supplied fields are invalid (XC-4)"
_INTERNAL_REASON = (
    "the request failed for a reason the API does not attribute to the caller — "
    "`message` never carries internal detail and the traceback is logged "
    "server-side (XC-14)"
)


def _render_reasons(reasons: list[str]) -> str:
    """Join cause fragments into one response description."""
    return f"Returned when {'; or when '.join(reasons)}."


# --- Components --------------------------------------------------------------


def _error_schemas() -> dict[str, Any]:
    """JSON Schema for design.md §1's envelope, as ``errors.py`` renders it.

    The ``code`` enum is read off ``ErrorCode`` rather than retyped, so the
    documented set and the raisable set cannot drift: adding a row to design.md
    §1's error table and to that enum documents itself here.
    """
    return {
        DETAIL_SCHEMA_NAME: {
            "title": DETAIL_SCHEMA_NAME,
            "type": "object",
            "required": ["code", "message"],
            "properties": {
                "code": {
                    "title": "Code",
                    "type": "string",
                    "enum": [code.value for code in ErrorCode],
                    "description": "Machine-readable error class. Closed set.",
                },
                "message": {
                    "title": "Message",
                    "type": "string",
                    "description": (
                        "Human-readable summary, safe to show a user. Never "
                        "carries server internals."
                    ),
                },
                "fields": {
                    "title": "Fields",
                    "type": "object",
                    "additionalProperties": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "description": (
                        "Per-field messages, keyed by field name. Present only "
                        "on `VALIDATION_ERROR`."
                    ),
                },
            },
        },
        ENVELOPE_SCHEMA_NAME: {
            "title": ENVELOPE_SCHEMA_NAME,
            "type": "object",
            "required": ["error"],
            "properties": {"error": {"$ref": DETAIL_REF}},
            "description": "The one shape every error response in this API uses.",
        },
    }


def _security_schemes() -> dict[str, Any]:
    """The two session cookies, described because nothing else in the spec can.

    Modelled as ``apiKey``/``cookie`` because that is OpenAPI's only vocabulary
    for a cookie-borne credential. ``httpOnly`` and ``Secure`` have no field to
    live in, so they are stated in the description — a reader otherwise assumes
    a token they can read and set themselves.
    """
    return {
        ACCESS_COOKIE_SCHEME: {
            "type": "apiKey",
            "in": "cookie",
            "name": ACCESS_COOKIE_NAME,
            "description": (
                "Session access token. Set by `POST /api/v1/auth/login` and "
                "`POST /api/v1/auth/refresh` as an `httpOnly`, `Secure`, "
                "`SameSite=Lax` cookie with a 1 hour lifetime. Sent "
                "automatically by the browser; not readable from JavaScript and "
                "not settable by a client."
            ),
        },
        REFRESH_COOKIE_SCHEME: {
            "type": "apiKey",
            "in": "cookie",
            "name": REFRESH_COOKIE_NAME,
            "description": (
                "Opaque refresh token, 30 day lifetime, same cookie attributes "
                f"as `{ACCESS_COOKIE_NAME}`. Read by "
                "`POST /api/v1/auth/refresh` only, which rotates it; replaying "
                "an already-rotated token revokes the whole family (AUTH-11)."
            ),
        },
    }


def _csrf_parameter() -> dict[str, Any]:
    """``X-Requested-With`` as a required header parameter on every write.

    A header parameter rather than an ``apiKey`` security scheme, which is the
    other way OpenAPI could express this. Three reasons: a security scheme
    applies globally or per-operation, so it would either claim ``GET``s need it
    or have to be listed on each write anyway; Swagger UI renders a security
    scheme in a modal a reader has to go looking for, and a required parameter
    in the operation itself; and *Try it out* actually sends a parameter, so a
    reader's first write from ``/docs`` succeeds rather than teaching them a
    ``403``. The value is unchecked — the protection is in the header being
    custom, not in what it says (see ``middleware.py``).
    """
    return {
        "name": CSRF_HEADER,
        "in": "header",
        "required": True,
        "schema": {
            "type": "string",
            "title": CSRF_HEADER,
            "default": "XMLHttpRequest",
        },
        "description": (
            "CSRF guard (XC-9). Any non-empty value. Enforced by middleware "
            "before routing, so a request without it is answered `403` without "
            "its body or its cookies being read — which is why it is absent "
            "from this operation's handler signature."
        ),
    }


def _envelope_content() -> dict[str, Any]:
    return {"application/json": {"schema": {"$ref": ENVELOPE_REF}}}


# --- Route introspection -----------------------------------------------------


def _dependency_calls(dependant: Any) -> Iterator[Callable[..., Any]]:
    """Every dependency callable in a route's tree, at any depth.

    Depth matters: the sub-resource routes reach ``get_current_user`` only
    through ``get_visible_parent_request``, and a one-level check would document
    them as unauthenticated.
    """
    for sub in dependant.dependencies:
        if sub.call is not None:
            yield sub.call
        yield from _dependency_calls(sub)


def _api_operations(app: FastAPI) -> Iterator[tuple[RouteContext, str]]:
    """Every (route, HTTP method) pair that appears in the document.

    Routers are nested rather than flattened in this FastAPI version, so
    ``app.routes`` on its own yields ``_IncludedRouter`` wrappers.
    ``iter_route_contexts`` is the same traversal ``get_openapi`` uses, which is
    what keeps this pass and the generated ``paths`` in step.
    """
    for route_context in iter_route_contexts(app.routes):
        if not isinstance(route_context.original_route, APIRoute):
            continue
        if not getattr(route_context, "include_in_schema", True):
            continue
        for method in route_context.methods or ():
            yield route_context, method.lower()


# --- Correction passes -------------------------------------------------------


def _drop_unreachable_validation_response(operation: dict[str, Any]) -> None:
    """Remove a documented ``422`` the operation has no way to produce.

    FastAPI attaches one to every operation that has *any* parameter. Path
    parameters on this API are always plain ``str`` — deliberately, so that a
    malformed id reaches the handler and is answered ``404`` like a missing row
    (XC-7, SR-13) rather than ``422`` before the handler runs. So an operation
    with no request body and nothing but path parameters cannot fail
    validation, and documenting a ``422`` there contradicts the requirement the
    ``str`` typing exists to satisfy.

    Called before ``X-Requested-With`` is injected, so that a header the
    middleware answers ``403`` for is never mistaken for a ``422`` source.
    """
    if "requestBody" in operation:
        return
    if any(p.get("in") != "path" for p in operation.get("parameters", ())):
        return
    operation.get("responses", {}).pop("422", None)


def _correct_operation(
    operation: dict[str, Any], route_context: RouteContext, method: str
) -> None:
    responses: dict[str, Any] = operation.setdefault("responses", {})

    # A route's own `responses=` entry carries a cause fragment and no content.
    # Read off the *route*, not off `operation`, and that is what makes this
    # pass idempotent: by the time it has run once, the operation's description
    # is a rendered sentence rather than the fragment it was built from, so a
    # second pass reading the operation back would find nothing left to
    # compose and would silently drop AUTH-2's 409 and CM-7's 403. A response
    # the route declared *with* content (`/health`'s 503, which is not an
    # envelope) is not a fragment and is left exactly as declared.
    declared: dict[str, str] = {
        str(status): response["description"]
        for status, response in (route_context.responses or {}).items()
        if "content" not in response and "description" in response
    }

    _drop_unreachable_validation_response(operation)

    calls = list(_dependency_calls(route_context.dependant))
    authenticated = get_current_user in calls
    # `require_role` stamps this on the dependency it builds, so the role gate
    # is recognised by a deliberate marker rather than by a closure's name that
    # a rename could silently change.
    role_gated = any(getattr(call, "required_role", None) for call in calls)
    state_changing = method.upper() not in SAFE_METHODS
    # Every path parameter in this API is a service request id resolved through
    # `visibility.py`; reaching one the caller may not see is SR-12's 404.
    resolves_path_resource = any(
        p.get("in") == "path" for p in operation.get("parameters", ())
    )

    reasons: dict[str, list[str]] = {status: [] for status in declared}

    if authenticated:
        reasons.setdefault("401", []).append(_UNAUTHENTICATED_REASON)
    if state_changing:
        reasons.setdefault("403", []).append(_CSRF_REASON)
    if role_gated:
        reasons.setdefault("403", []).append(_ROLE_REASON)
    if resolves_path_resource:
        reasons.setdefault("404", []).append(_NOT_FOUND_REASON)
    if "422" in responses:
        reasons.setdefault("422", []).append(_VALIDATION_REASON)
    reasons.setdefault("500", []).append(_INTERNAL_REASON)

    for status, fragments in reasons.items():
        # The route-declared fragment goes last: on `403` the structural CSRF
        # check is what a request meets first, so the description reads in the
        # order the runtime applies them.
        if declared.get(status):
            fragments = [*fragments, declared[status]]
        responses[status] = {
            "description": _render_reasons(fragments),
            "content": _envelope_content(),
        }

    if authenticated and "security" not in operation:
        operation["security"] = [{ACCESS_COOKIE_SCHEME: []}]

    if state_changing:
        parameters = operation.setdefault("parameters", [])
        if not any(
            p.get("name") == CSRF_HEADER and p.get("in") == "header"
            for p in parameters
        ):
            parameters.append(_csrf_parameter())


def _correct(app: FastAPI, schema: dict[str, Any]) -> dict[str, Any]:
    """Apply every correction in place. Idempotent — see ``use_corrected_openapi``."""
    schema["info"]["version"] = SPEC_VERSION
    schema["info"]["description"] = API_DESCRIPTION

    components = schema.setdefault("components", {})
    components.setdefault("schemas", {}).update(_error_schemas())
    for name in _STOCK_VALIDATION_SCHEMAS:
        components["schemas"].pop(name, None)
    components["securitySchemes"] = _security_schemes()

    by_key = {
        (route_context.path_format, method): (route_context, method)
        for route_context, method in _api_operations(app)
    }
    for path, operations in schema.get("paths", {}).items():
        for method, operation in operations.items():
            found = by_key.get((path, method))
            if found is None:  # pragma: no cover - every documented path is a route
                continue
            _correct_operation(operation, *found)
    return schema


def use_corrected_openapi(app: FastAPI) -> None:
    """Wrap ``app.openapi`` so the served document is the corrected one.

    Wraps rather than replaces FastAPI's generator, so its caching and its cache
    invalidation still apply. It hands back the same cached dict every time and
    the corrections mutate it in place, which is why every pass above is written
    to be idempotent — a second run must not append a second
    ``X-Requested-With`` parameter or re-render a description onto itself.
    """
    generate = app.openapi

    def corrected() -> dict[str, Any]:
        return _correct(app, generate())

    app.openapi = corrected  # type: ignore[method-assign]


def spec_json(app: FastAPI | None = None) -> str:
    """The document as the checked-in ``openapi.json`` holds it.

    Pretty-printed so a regeneration lands as a readable diff; the bytes
    ``/openapi.json`` serves are the same document with different whitespace,
    which ``tests/api/test_openapi.py`` pins by comparing the parsed documents.
    """
    if app is None:
        from app.main import create_app

        app = create_app()
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":  # pragma: no cover - regeneration entrypoint
    import pathlib

    # `python -m app.api.openapi`, run from `backend/`.
    target = pathlib.Path(__file__).resolve().parents[2] / "openapi.json"
    target.write_text(spec_json(), encoding="utf-8")
    print(f"wrote {target}")
