"""The generated spec against the app it claims to describe (T-DOCS-0).

These tests exist because the previous spec was *wrong* rather than merely
thin: it documented FastAPI's ``{"detail": [...]}`` on every route, which is
precisely the shape ``register_exception_handlers`` replaces, so a client
generated from it parsed the one key the API never sends. A correction that
lives in a post-processing pass is exactly the kind that can look applied and
not be, so nothing below reads the override; every assertion parses the
generated document, and the structural ones re-derive what they expect from
the route table rather than from the module that wrote it.

No database is required here. The app is built by the real ``create_app()``
and only introspected, apart from two runtime cross-checks that are answered
before any handler touches a session.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.middleware import CSRF_HEADER, SAFE_METHODS
from app.api.openapi import ENVELOPE_REF, SPEC_VERSION, spec_json
from app.core.security import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME
from app.main import create_app

# .../backend/tests/api/test_openapi.py -> parents[2] == .../backend
CHECKED_IN_SPEC = Path(__file__).resolve().parents[2] / "openapi.json"

ENVELOPE_CONTENT = {"application/json": {"schema": {"$ref": ENVELOPE_REF}}}


@pytest.fixture(scope="module")
def app() -> FastAPI:
    return create_app()


@pytest.fixture(scope="module")
def spec(app: FastAPI) -> dict[str, Any]:
    return app.openapi()


def _operations(spec: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    for path, methods in spec["paths"].items():
        for method, operation in methods.items():
            yield path, method, operation


def _uses_current_user(dependant: Any) -> bool:
    """Re-derived here rather than imported from ``app.api.openapi``.

    Sharing the traversal with the code under test would make every structural
    assertion below self-consistent instead of correct — a walk that stopped at
    depth one would document the sub-resource routes as unauthenticated *and*
    expect them to be.
    """
    for sub in dependant.dependencies:
        if sub.call is get_current_user:
            return True
        if _uses_current_user(sub):
            return True
    return False


@pytest.fixture(scope="module")
def route_facts(app: FastAPI) -> dict[tuple[str, str], dict[str, bool]]:
    """What each documented operation actually is, read off the route table."""
    facts: dict[tuple[str, str], dict[str, bool]] = {}
    for route_context in iter_route_contexts(app.routes):
        if not isinstance(route_context.original_route, APIRoute):
            continue
        for method in route_context.methods or ():
            facts[(route_context.path_format, method.lower())] = {
                "authenticated": _uses_current_user(route_context.dependant),
                "state_changing": method.upper() not in SAFE_METHODS,
                "path_resource": "{" in (route_context.path_format or ""),
            }
    return facts


def test_the_document_describes_every_route(spec, route_facts):
    """A guard on every other test here: an empty sweep proves nothing."""
    documented = {(path, method) for path, method, _ in _operations(spec)}
    assert documented == set(route_facts)
    assert len(documented) == 15


# --- The 422 shape (the headline correction) ---------------------------------


def test_every_documented_422_is_the_error_envelope(spec):
    """XC-4's envelope, not FastAPI's ``HTTPValidationError``."""
    documented = [
        (path, method)
        for path, method, operation in _operations(spec)
        if "422" in operation["responses"]
    ]
    # Non-vacuous on purpose: if a future change stopped generating 422s at
    # all, every assertion in the loop would pass by not running.
    assert len(documented) == 8

    for path, method, operation in _operations(spec):
        response = operation["responses"].get("422")
        if response is None:
            continue
        assert response["content"] == ENVELOPE_CONTENT, f"{method.upper()} {path}"


def test_the_stock_validation_schemas_are_gone(spec):
    schemas = spec["components"]["schemas"]
    assert "HTTPValidationError" not in schemas
    assert "ValidationError" not in schemas


def test_no_error_response_anywhere_documents_a_detail_key(spec):
    """The failure this whole task was about, asserted over the whole document.

    ``detail`` is the key FastAPI would have documented and the key this API
    never sends; nothing generated from this spec should look for it.
    """
    for path, method, operation in _operations(spec):
        for status, response in operation["responses"].items():
            if not status.startswith(("4", "5")):
                continue
            schema = (
                response.get("content", {})
                .get("application/json", {})
                .get("schema", {})
            )
            assert "detail" not in json.dumps(schema), f"{method.upper()} {path} {status}"


def test_the_envelope_schema_matches_what_errors_py_renders(spec):
    from app.api.errors import ErrorCode

    envelope = spec["components"]["schemas"]["ErrorEnvelope"]
    assert envelope["required"] == ["error"]
    detail = spec["components"]["schemas"]["ErrorDetail"]
    assert detail["required"] == ["code", "message"]
    assert set(detail["properties"]) == {"code", "message", "fields"}
    assert detail["properties"]["code"]["enum"] == [c.value for c in ErrorCode]


def test_a_route_that_cannot_fail_validation_documents_no_422(spec):
    """SR-13's 404 is the answer for a malformed id, so a 422 there is a lie.

    ``GET /service-requests/{request_id}`` takes a ``str`` path parameter and
    nothing else — FastAPI documented a 422 for it anyway, contradicting the
    requirement the ``str`` typing exists to satisfy.
    """
    operation = spec["paths"]["/api/v1/service-requests/{request_id}"]["get"]
    assert "422" not in operation["responses"]


# --- Structural error statuses -----------------------------------------------


def test_every_authenticated_route_documents_401(spec, route_facts):
    authenticated = [key for key, f in route_facts.items() if f["authenticated"]]
    assert len(authenticated) == 8
    for path, method in authenticated:
        response = spec["paths"][path][method]["responses"].get("401")
        assert response is not None, f"{method.upper()} {path}"
        assert response["content"] == ENVELOPE_CONTENT
        assert ACCESS_COOKIE_NAME in response["description"]


def test_no_unauthenticated_route_claims_a_401(spec, route_facts):
    """``POST /auth/logout`` is the one that matters: AUTH-13 makes it 204 always."""
    for (path, method), facts in route_facts.items():
        if facts["authenticated"]:
            continue
        operation = spec["paths"][path][method]
        if "401" not in operation["responses"]:
            continue
        # The only unauthenticated routes that can 401 are the two that check a
        # credential by hand rather than through `get_current_user`.
        assert (path, method) in {
            ("/api/v1/auth/login", "post"),
            ("/api/v1/auth/refresh", "post"),
        }
    assert "401" not in spec["paths"]["/api/v1/auth/logout"]["post"]["responses"]


def test_every_write_documents_403_and_requires_the_csrf_header(spec, route_facts):
    writes = [key for key, f in route_facts.items() if f["state_changing"]]
    assert len(writes) == 7
    for path, method in writes:
        operation = spec["paths"][path][method]
        assert operation["responses"]["403"]["content"] == ENVELOPE_CONTENT
        assert CSRF_HEADER in operation["responses"]["403"]["description"]
        headers = [
            p
            for p in operation.get("parameters", [])
            if p["in"] == "header" and p["name"] == CSRF_HEADER
        ]
        assert len(headers) == 1, f"{method.upper()} {path}"
        assert headers[0]["required"] is True


def test_no_safe_method_asks_for_the_csrf_header(spec, route_facts):
    """It is exempt on GET/HEAD/OPTIONS (middleware.py), so documenting it would
    send readers looking for a header that does nothing."""
    for (path, method), facts in route_facts.items():
        if facts["state_changing"]:
            continue
        names = [p["name"] for p in spec["paths"][path][method].get("parameters", [])]
        assert CSRF_HEADER not in names, f"{method.upper()} {path}"


def test_every_path_parameter_route_documents_404(spec, route_facts):
    with_path_param = [key for key, f in route_facts.items() if f["path_resource"]]
    assert len(with_path_param) == 5
    for path, method in with_path_param:
        response = spec["paths"][path][method]["responses"].get("404")
        assert response is not None, f"{method.upper()} {path}"
        assert response["content"] == ENVELOPE_CONTENT


def test_every_operation_documents_500(spec):
    for path, method, operation in _operations(spec):
        response = operation["responses"].get("500")
        assert response is not None, f"{method.upper()} {path}"
        assert response["content"] == ENVELOPE_CONTENT


# --- Route-specific statuses -------------------------------------------------


def test_register_is_the_only_route_documenting_409(spec):
    with_conflict = [
        (path, method)
        for path, method, operation in _operations(spec)
        if "409" in operation["responses"]
    ]
    assert with_conflict == [("/api/v1/auth/register", "post")]


def test_the_admin_gated_write_documents_both_of_its_403_causes(spec):
    description = spec["paths"][
        "/api/v1/service-requests/{request_id}/status-changes"
    ]["post"]["responses"]["403"]["description"]
    assert CSRF_HEADER in description
    assert "XC-6" in description


def test_the_comment_write_documents_cm7_alongside_csrf(spec):
    description = spec["paths"]["/api/v1/service-requests/{request_id}/comments"][
        "post"
    ]["responses"]["403"]["description"]
    assert CSRF_HEADER in description
    assert "CM-7" in description


def test_health_db_documents_its_503_with_its_own_body_not_the_envelope(spec):
    """The one error response in the API that is not the envelope.

    It is built as a plain ``JSONResponse`` in the handler, so it never reaches
    the exception handlers — documenting it as an envelope would be the same
    class of untruth this task exists to remove.
    """
    response = spec["paths"]["/health/db"]["get"]["responses"]["503"]
    schema = response["content"]["application/json"]["schema"]
    assert "$ref" not in schema
    assert set(schema["properties"]) == {"status", "db"}


# --- Security ----------------------------------------------------------------


def test_security_schemes_describe_the_session_cookies(spec):
    schemes = spec["components"]["securitySchemes"]
    assert schemes is not None
    access = schemes["accessTokenCookie"]
    assert (access["type"], access["in"], access["name"]) == (
        "apiKey",
        "cookie",
        ACCESS_COOKIE_NAME,
    )
    refresh = schemes["refreshTokenCookie"]
    assert (refresh["type"], refresh["in"], refresh["name"]) == (
        "apiKey",
        "cookie",
        REFRESH_COOKIE_NAME,
    )


def test_the_cookie_scheme_is_applied_to_every_authenticated_route(spec, route_facts):
    for (path, method), facts in route_facts.items():
        operation = spec["paths"][path][method]
        if facts["authenticated"]:
            assert operation["security"] == [{"accessTokenCookie": []}], (
                f"{method.upper()} {path}"
            )
        elif path != "/api/v1/auth/refresh":
            assert "security" not in operation, f"{method.upper()} {path}"


def test_refresh_declares_the_refresh_cookie_rather_than_the_access_cookie(spec):
    operation = spec["paths"]["/api/v1/auth/refresh"]["post"]
    assert operation["security"] == [{"refreshTokenCookie": []}]


def test_the_csrf_requirement_is_findable_before_a_first_failed_write(spec):
    """A reader of ``/docs`` alone must meet XC-9 somewhere they cannot miss.

    The per-operation header parameter is the main answer; this pins the other
    half, the API description Swagger UI renders at the top of the page, so the
    requirement is visible without opening a single operation first.
    """
    description = spec["info"]["description"]
    assert CSRF_HEADER in description
    assert "403" in description


def test_the_spec_version_is_no_longer_fastapis_default(spec):
    assert spec["info"]["version"] == SPEC_VERSION != "0.1.0"


# --- The checked-in file -----------------------------------------------------


def test_the_checked_in_spec_matches_the_served_one(app):
    """One document, generated; never two hand-maintained ones.

    Compared parsed rather than byte-for-byte: the file is pretty-printed for
    readable diffs and ``/openapi.json`` is served compact, so the bytes differ
    by whitespace alone. Regenerate with ``python -m app.api.openapi``.
    """
    assert CHECKED_IN_SPEC.exists(), f"{CHECKED_IN_SPEC} is missing"
    on_disk = json.loads(CHECKED_IN_SPEC.read_text(encoding="utf-8"))
    assert on_disk == app.openapi()
    # And the exporter is what produced it, so a regeneration is a no-op diff.
    assert CHECKED_IN_SPEC.read_text(encoding="utf-8") == spec_json(app)


def test_the_served_document_is_the_corrected_one(app, spec):
    """Guards against the correction being applied to an object nobody serves."""
    with TestClient(app) as client:
        served = client.get("/openapi.json")
    assert served.status_code == 200
    assert served.json() == spec


def test_regenerating_the_document_does_not_change_it():
    """The passes mutate FastAPI's cached dict in place, so they must be
    idempotent — a second call must not append a second ``X-Requested-With``
    parameter, or re-render a description onto itself, or lose a route-declared
    cause fragment that the first pass has already folded into a sentence.

    Builds its **own** app rather than taking the module fixture, and compares
    the first two passes specifically. The real defect here (caught during
    T-DOCS-0) lost AUTH-2's 409 wording on pass two and was stable from pass
    three on, so a test comparing two late passes of an app other tests had
    already rendered would have gone green on it.
    """
    own = create_app()
    first = json.dumps(own.openapi(), sort_keys=True)
    assert json.dumps(own.openapi(), sort_keys=True) == first


# --- Documentation against runtime -------------------------------------------
#
# Two checks that a documented status is the one actually sent. Both are
# answered before any handler opens a database session, which is what lets them
# live in a test module that needs no Postgres.


def test_a_write_without_the_csrf_header_really_answers_the_documented_403(app, spec):
    with TestClient(app) as client:
        response = client.post("/api/v1/auth/login", json={})
    assert response.status_code == 403
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) <= {"code", "message", "fields"}
    assert body["error"]["code"] == "FORBIDDEN"
    assert "403" in spec["paths"]["/api/v1/auth/login"]["post"]["responses"]


def test_an_unauthenticated_read_really_answers_the_documented_401(app, spec):
    with TestClient(app) as client:
        response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert "401" in spec["paths"]["/api/v1/auth/me"]["get"]["responses"]
