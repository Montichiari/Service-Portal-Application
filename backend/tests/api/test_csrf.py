"""XC-9 — the ``X-Requested-With`` CSRF check (T-AUTH-2; design.md §1)."""

from __future__ import annotations

import pytest

from app.api.middleware import CSRF_HEADER
from tests.api.conftest import CSRF_HEADERS, TEST_PREFIX

UNSAFE_METHODS = ["post", "put", "patch", "delete"]


def assert_forbidden(response) -> None:
    assert response.status_code == 403
    body = response.json()
    assert "detail" not in body
    assert body["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize("method", UNSAFE_METHODS)
def test_every_unsafe_method_requires_the_header(client, method):
    # An unrouted path on purpose: the check has to happen before routing, so
    # it must fire even where no route exists to protect.
    assert_forbidden(getattr(client, method)("/api/v1/anything"))


@pytest.mark.parametrize("method", UNSAFE_METHODS)
def test_the_header_lets_the_request_through_to_routing(client, method):
    response = getattr(client, method)("/api/v1/anything", headers=CSRF_HEADERS)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_an_empty_header_value_is_not_enough(client):
    assert_forbidden(client.post(f"{TEST_PREFIX}/echo", headers={CSRF_HEADER: ""}))


def test_any_non_empty_value_is_accepted(client):
    # The protection is that the header is custom, not what it says — see the
    # middleware docstring. Pinning the value would break clients for no gain.
    response = client.post(
        f"{TEST_PREFIX}/echo", json={"title": "ok"}, headers={CSRF_HEADER: "fetch"}
    )

    assert response.status_code == 200


def test_the_check_runs_before_authentication(client):
    # No cookie *and* no header. XC-9 requires the header check to win, so a
    # rejected request never has its cookies inspected.
    assert_forbidden(client.post(f"{TEST_PREFIX}/protected"))


def test_the_check_runs_before_body_validation(client):
    # An invalid body that would otherwise be a 422 — 403 proves nothing
    # parsed the body first.
    assert_forbidden(client.post(f"{TEST_PREFIX}/echo", json={"title": ""}))


def test_a_valid_post_still_succeeds_with_the_header(client):
    response = client.post(
        f"{TEST_PREFIX}/echo", json={"title": "ok"}, headers=CSRF_HEADERS
    )

    assert response.status_code == 200
    assert response.json() == {"title": "ok", "limit": 1}


def test_get_is_exempt(client):
    assert client.get(f"{TEST_PREFIX}/open").status_code == 200


def test_head_is_exempt(client):
    # 405, not 200: FastAPI doesn't route HEAD to a GET handler the way bare
    # Starlette does. What matters here is only that it isn't a 403 — the
    # request reached routing rather than being stopped by the CSRF check.
    assert client.head(f"{TEST_PREFIX}/open").status_code != 403


def test_options_is_exempt(client):
    # The CORS preflight the browser sends itself, which can never carry a
    # custom header. Blocking it would break every cross-origin write.
    response = client.options(f"{TEST_PREFIX}/open")

    assert response.status_code != 403
