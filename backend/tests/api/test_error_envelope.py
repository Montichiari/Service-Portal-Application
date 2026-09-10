"""XC-4 and the error envelope generally (T-AUTH-2; design.md §1).

Every assertion here checks the whole envelope, not just the status code —
backend/CLAUDE.md's API testing rule: a right status code with a wrong
``fields`` map is still a broken contract.

The catch-all ``500`` handler has its own file, ``test_internal_error.py``
(XC-14), because it has four distinct origins to cover.
"""

from __future__ import annotations

from tests.api.conftest import CSRF_HEADERS, TEST_PREFIX

ECHO = f"{TEST_PREFIX}/echo"


def test_validation_error_uses_custom_envelope(client):
    response = client.post(ECHO, json={}, headers=CSRF_HEADERS)

    assert response.status_code == 422
    body = response.json()
    # FastAPI's default shape is {"detail": [...]}. Its absence is the point
    # of XC-4, so it's asserted explicitly rather than implied.
    assert "detail" not in body
    assert set(body) == {"error"}
    error = body["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert isinstance(error["message"], str) and error["message"]
    assert list(error["fields"]) == ["title"]
    assert error["fields"]["title"], "the failing field must carry a message"


def test_every_failing_field_appears_in_fields(client):
    response = client.post(
        f"{ECHO}?limit=not-an-int",
        json={"title": "far too long to fit", "tags": [{"name": ""}]},
        headers=CSRF_HEADERS,
    )

    assert response.status_code == 422
    fields = response.json()["error"]["fields"]
    # Body, nested-list-item and query-param locations all map to a key, and
    # none of them keeps Pydantic's location prefix.
    assert set(fields) == {"title", "tags.0.name", "limit"}
    assert not any(key.startswith(("body.", "query.")) for key in fields)


def test_repeated_failures_on_one_field_collect_into_a_list(client):
    response = client.post(
        ECHO,
        json={"title": "ok", "tags": [{"name": ""}, {"name": ""}]},
        headers=CSRF_HEADERS,
    )

    fields = response.json()["error"]["fields"]
    # Two separate list entries failed, so they must not collide onto one key.
    assert set(fields) == {"tags.0.name", "tags.1.name"}
    assert all(len(messages) == 1 for messages in fields.values())


def test_validation_error_never_echoes_the_rejected_input(client):
    # Stand-in for the case that actually matters: a register call whose
    # password fails validation must not have that password reflected back.
    secret = "correct-horse-battery-staple"
    response = client.post(ECHO, json={"title": secret}, headers=CSRF_HEADERS)

    assert response.status_code == 422
    assert secret not in response.text


def test_unparseable_body_still_returns_the_envelope(client):
    response = client.post(
        ECHO,
        content=b"{not json",
        headers={**CSRF_HEADERS, "Content-Type": "application/json"},
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    # No field is identifiable, so the whole-body location is the key.
    assert "body" in error["fields"]


def test_fields_is_absent_on_non_validation_errors(raw_client):
    for response in (
        raw_client.get(f"{TEST_PREFIX}/boom"),
        raw_client.get(f"{TEST_PREFIX}/protected"),
    ):
        # design.md §1: `fields` is present only for VALIDATION_ERROR, so its
        # presence is a meaningful signal rather than an empty map to check.
        assert "fields" not in response.json()["error"]


def test_unrouted_path_uses_the_envelope(client):
    response = client.get("/api/v1/no-such-route")

    assert response.status_code == 404
    body = response.json()
    assert "detail" not in body
    assert body["error"]["code"] == "NOT_FOUND"


def test_wrong_method_uses_the_envelope_and_keeps_its_headers(client):
    response = client.put(f"{TEST_PREFIX}/open", headers=CSRF_HEADERS)

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "BAD_REQUEST"
    # A 405 without `Allow` is non-conformant; re-rendering the body must not
    # drop the headers the framework attached.
    assert "Allow" in response.headers
