"""XC-12 — CORS (T-AUTH-3; design.md §1).

The success path is the easy half and the half that proves least. What
actually breaks a frontend is an *error* response arriving without CORS
headers: the browser hands `fetch` an opaque network failure instead of a
readable status and envelope body, so `T-AUTH-4`'s client can see that
something went wrong but never what. Every status code XC-12 names is
therefore checked here, not just ``200``.

The origin checks run against ``settings.FRONTEND_ORIGIN`` rather than a
literal, so pointing a deployment at a different frontend can't leave these
passing against the wrong host.
"""

from __future__ import annotations

import uuid

from app.api.cors import ALLOWED_ORIGINS
from app.api.middleware import CSRF_HEADER
from app.config import settings
from tests.api.conftest import CSRF_HEADERS, TEST_PREFIX

ORIGIN = settings.FRONTEND_ORIGIN
OTHER_ORIGIN = "https://not-our-frontend.example"

AUTH = "/api/v1/auth"
LOGIN = f"{AUTH}/login"
REGISTER = f"{AUTH}/register"

ALLOW_ORIGIN = "access-control-allow-origin"
ALLOW_CREDENTIALS = "access-control-allow-credentials"


def assert_cors_allowed(response) -> None:
    """The two headers a credentialed cross-origin read depends on."""
    assert response.headers.get(ALLOW_ORIGIN) == ORIGIN, dict(response.headers)
    # Without this the browser discards the response *and* refuses to send or
    # store the auth cookies — which are the entire auth transport here.
    assert response.headers.get(ALLOW_CREDENTIALS) == "true"


# --- configuration -----------------------------------------------------------


def test_the_allowed_origin_is_explicit_and_never_a_wildcard():
    # Not style: the CORS spec forbids combining a wildcard origin with
    # credentials, so `*` wouldn't be a loose shortcut here, it would be a
    # broken one that fails every cookie-bearing call.
    assert ALLOWED_ORIGINS == (settings.FRONTEND_ORIGIN,)
    assert "*" not in ALLOWED_ORIGINS


# --- preflight ---------------------------------------------------------------


def test_preflight_from_the_frontend_origin_is_approved(client):
    response = client.options(
        LOGIN,
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": f"content-type,{CSRF_HEADER.lower()}",
        },
    )

    assert response.status_code == 200
    assert_cors_allowed(response)
    allowed_headers = response.headers.get("access-control-allow-headers", "").lower()
    # XC-9's header has to be approved by the preflight or the browser blocks
    # the real request — the CSRF check and CORS would then cancel each other
    # out, each looking correct in isolation.
    assert CSRF_HEADER.lower() in allowed_headers
    assert "post" in response.headers.get("access-control-allow-methods", "").lower()


def test_preflight_from_another_origin_is_refused(client):
    response = client.options(
        LOGIN,
        headers={
            "Origin": OTHER_ORIGIN,
            "Access-Control-Request-Method": "POST",
        },
    )

    assert ALLOW_ORIGIN not in response.headers
    assert response.status_code == 400


def test_the_preflight_is_not_blocked_by_the_csrf_check(client):
    # A browser cannot attach a custom header to its own preflight, so if the
    # CSRF middleware ever stopped exempting OPTIONS, every cross-origin write
    # would fail before the real request was attempted (XC-9).
    response = client.options(
        REGISTER,
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"},
    )

    assert response.status_code != 403


# --- real requests: success and every error status XC-12 names ---------------


def test_a_successful_response_carries_cors_headers(auth_client):
    payload = {
        "first_name": "Daniel",
        "last_name": "Osei",
        "email": f"cors-{uuid.uuid4().hex[:12]}@example.com",
        "password": "correct horse battery staple",
    }

    response = auth_client.post(REGISTER, json=payload, headers={"Origin": ORIGIN})

    assert response.status_code == 201
    assert_cors_allowed(response)


def test_a_401_carries_cors_headers(auth_client):
    # The case the acceptance criterion calls out: without these headers the
    # frontend cannot read `error.code` off a failed login, only that "the
    # network failed".
    response = auth_client.post(
        LOGIN,
        json={"email": "nobody@example.com", "password": "wrong wrong wrong"},
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert_cors_allowed(response)


def test_a_422_carries_cors_headers(auth_client):
    response = auth_client.post(
        REGISTER, json={"first_name": ""}, headers={"Origin": ORIGIN}
    )

    assert response.status_code == 422
    # A validation error the user can't see is a form that can't show which
    # field was wrong.
    assert response.json()["error"]["fields"]
    assert_cors_allowed(response)


def test_a_403_from_the_csrf_middleware_carries_cors_headers(client):
    # Produced by middleware, before routing. It reaches the browser only
    # because CORS is registered *outside* the CSRF check — reverse the two
    # registrations and this is the test that notices.
    response = client.post(LOGIN, json={}, headers={"Origin": ORIGIN})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert_cors_allowed(response)


def test_a_404_carries_cors_headers(client):
    response = client.get("/api/v1/no-such-route", headers={"Origin": ORIGIN})

    assert response.status_code == 404
    assert_cors_allowed(response)


def test_a_500_carries_cors_headers(raw_client):
    """The one response created outside ``CORSMiddleware`` (see app/api/cors.py).

    Starlette hangs the ``Exception`` handler off ``ServerErrorMiddleware``,
    the outermost layer of all, so this response never passes back through
    CORS and has to carry the headers itself.
    """
    response = raw_client.get(f"{TEST_PREFIX}/boom", headers={"Origin": ORIGIN})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert_cors_allowed(response)


def test_a_500_still_leaks_nothing_when_it_carries_cors_headers(raw_client):
    # Guards against "fixing" the headers by hand-building a response that
    # skips `error_response` and its generic message.
    from tests.api.conftest import ROUTE_LEAK

    response = raw_client.get(f"{TEST_PREFIX}/boom", headers={"Origin": ORIGIN})

    assert ROUTE_LEAK not in response.text
    assert "Traceback" not in response.text


# --- other origins get nothing ------------------------------------------------


def test_another_origin_gets_no_cors_headers_on_success(auth_client):
    response = auth_client.post(
        LOGIN,
        json={"email": "nobody@example.com", "password": "wrong wrong wrong"},
        headers={"Origin": OTHER_ORIGIN},
    )

    # Starlette answers the request and omits the headers; the browser is what
    # refuses to hand the body to the calling script. Asserting their absence
    # is what "rejected by CORS" means for a non-preflight request.
    assert ALLOW_ORIGIN not in response.headers


def test_another_origin_gets_no_cors_headers_on_a_500(raw_client):
    response = raw_client.get(f"{TEST_PREFIX}/boom", headers={"Origin": OTHER_ORIGIN})

    # The hand-written path in `cors_headers_for` must apply the same origin
    # check as the middleware, not blanket-echo whatever arrived.
    assert response.status_code == 500
    assert ALLOW_ORIGIN not in response.headers


def test_a_same_origin_request_gets_no_cors_headers(client):
    # No `Origin` header at all — a server-to-server call or a same-origin
    # fetch. Emitting `Access-Control-Allow-Origin: null` or echoing an empty
    # origin here would be worse than emitting nothing.
    response = client.get(f"{TEST_PREFIX}/open", headers=CSRF_HEADERS)

    assert ALLOW_ORIGIN not in response.headers
