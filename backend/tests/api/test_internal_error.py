"""XC-14 — the catch-all 500 handler (T-AUTH-2, reopened on review).

The handler itself was built and tested with T-AUTH-2's original work; these
tests widen that coverage to XC-14's wording as it was finally written, which
is more specific in two ways:

* **"anywhere while processing a request"** — not just a route body. A
  dependency, response serialization and the middleware stack are each a
  separate code path reaching the handler, and each is exercised below.
* **"never includes the exception's message, type, stack trace, or any
  internal file path"** — file paths and the exception's type name are named
  explicitly, so they're asserted explicitly.

Every case runs through ``raise_server_exceptions=False``: Starlette's
``ServerErrorMiddleware`` re-raises after its handler has produced a response,
so the default client would surface the exception instead of the response a
real client receives.
"""

from __future__ import annotations

import logging

import pytest

from tests.api.conftest import (
    DEPENDENCY_LEAK,
    EXPLODE_HEADER,
    MIDDLEWARE_LEAK,
    ROUTE_LEAK,
    SERIALIZATION_LEAK,
    TEST_PREFIX,
)


def assert_generic_500(response, leaked: str) -> None:
    """The full XC-14 contract, asserted in one place for every origin."""
    assert response.status_code == 500

    # Starlette's own fallback for an unhandled exception is a plain-text
    # "Internal Server Error" body. XC-14 rules that out by name, and it is
    # not detectable from the status code alone.
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert set(body) == {"error"}
    error = body["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert error["message"]
    # design.md §1: `fields` belongs to VALIDATION_ERROR only.
    assert "fields" not in error

    text = response.text
    assert leaked not in text, "the exception's own message reached the client"
    # The exception's *type* is named by XC-14 alongside its message.
    assert "RuntimeError" not in text
    assert "ValidationError" not in text
    # A stack trace, and the file paths one is made of. ".py" catches a
    # rendered traceback; "app\\" / "app/" catches a bare module path.
    assert "Traceback" not in text
    assert ".py" not in text
    assert "app/" not in text and "app\\" not in text


def test_exception_raised_in_a_route_body(raw_client):
    assert_generic_500(raw_client.get(f"{TEST_PREFIX}/boom"), ROUTE_LEAK)


def test_exception_raised_in_a_dependency(raw_client):
    # The realistic case once T-AUTH-3 lands: `get_current_user`'s query
    # failing means the exception is raised before the route body ever runs.
    assert_generic_500(
        raw_client.get(f"{TEST_PREFIX}/boom-dependency"), DEPENDENCY_LEAK
    )


def test_exception_raised_while_serializing_the_response(raw_client):
    # FastAPI's ResponseValidationError carries the offending value in its
    # message. In a real route that value is whatever the response model was
    # there to exclude — a password hash, an internal note — so this is the
    # case where a naive `str(exc)` in the handler leaks something that
    # matters.
    assert_generic_500(
        raw_client.get(f"{TEST_PREFIX}/boom-serialization"), SERIALIZATION_LEAK
    )


def test_exception_raised_inside_the_middleware_stack(exploding_middleware_client):
    # Proves the handler is outside the user middleware stack, not inside it.
    assert_generic_500(
        exploding_middleware_client.get(
            f"{TEST_PREFIX}/open", headers={EXPLODE_HEADER: "1"}
        ),
        MIDDLEWARE_LEAK,
    )


def test_a_normal_request_still_succeeds_through_that_stack(
    exploding_middleware_client,
):
    # Guards the test above from passing vacuously: without this, a fixture
    # that failed every request would look like proof the handler works.
    response = exploding_middleware_client.get(f"{TEST_PREFIX}/open")

    assert response.status_code == 200


def test_the_traceback_is_logged_even_though_it_is_not_returned(
    raw_client, caplog: pytest.LogCaptureFixture
):
    # The other half of not leaking: the detail has to survive somewhere the
    # operator can reach it. Without this, "stop logging it" would read as a
    # valid fix for a leak test.
    with caplog.at_level(logging.ERROR, logger="app.api.errors"):
        raw_client.get(f"{TEST_PREFIX}/boom")

    assert ROUTE_LEAK in caplog.text
    assert "Traceback" in caplog.text
