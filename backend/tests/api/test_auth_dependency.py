"""XC-5 and XC-6 — ``get_current_user`` and ``require_role`` (T-AUTH-2)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.api.deps import require_role
from app.core.security import ACCESS_COOKIE_NAME, create_access_token
from app.config import settings
from tests.api.conftest import TEST_PREFIX

PROTECTED = f"{TEST_PREFIX}/protected"
ADMIN_ONLY = f"{TEST_PREFIX}/admin"
USER_OR_ABOVE = f"{TEST_PREFIX}/user-or-above"


def assert_unauthenticated(response) -> None:
    assert response.status_code == 401
    body = response.json()
    assert "detail" not in body
    assert body["error"]["code"] == "UNAUTHENTICATED"
    assert body["error"]["message"]


# --- XC-5: authentication ----------------------------------------------------


def test_no_cookie_returns_401_envelope(client):
    assert_unauthenticated(client.get(PROTECTED))


def test_valid_cookie_resolves_the_user(client, make_user, cookie_header):
    user = make_user(first_name="Ada")

    response = client.get(PROTECTED, headers=cookie_header(user))

    assert response.status_code == 200
    assert response.json() == {"id": str(user.id), "role": "user"}


def test_expired_token_returns_401(client, make_user, cookie_header):
    user = make_user()
    # Issued two hours ago, so its 1-hour `exp` is comfortably past.
    issued = datetime.now(timezone.utc) - timedelta(hours=2)

    assert_unauthenticated(client.get(PROTECTED, headers=cookie_header(user, now=issued)))


def test_token_signed_with_another_key_returns_401(client, make_user, cookie_header):
    user = make_user()
    # A structurally perfect token with entirely valid claims — only the
    # signature is wrong. Corrupting the encoding instead would fail at
    # parsing, before the signature check this test exists to exercise
    # (T-AUTH-1's finding, recorded in tasks.md).
    forged = jwt.encode(
        {
            "sub": str(user.id),
            "role": "admin",
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
            "jti": uuid.uuid4().hex,
        },
        settings.JWT_SECRET_KEY + "-wrong",
        algorithm=settings.JWT_ALGORITHM,
    )

    assert_unauthenticated(client.get(PROTECTED, headers=cookie_header(user, token=forged)))


def test_unsigned_alg_none_token_returns_401(client, make_user, cookie_header):
    user = make_user()
    unsigned = jwt.encode(
        {
            "sub": str(user.id),
            "role": "admin",
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
            "jti": uuid.uuid4().hex,
        },
        key="",
        algorithm="none",
    )

    assert_unauthenticated(client.get(PROTECTED, headers=cookie_header(user, token=unsigned)))


def test_token_for_a_deleted_user_returns_401_not_500(client, cookie_header):
    class _Ghost:
        id = uuid.uuid4()
        role = "user"

    # Well-signed, unexpired, and referring to nobody. Trusting the claims
    # blindly would let this reach a route and fail later as a foreign-key
    # violation — a 500 where 401 is the honest answer.
    assert_unauthenticated(client.get(PROTECTED, headers=cookie_header(_Ghost())))


def test_token_for_a_deactivated_user_returns_401(client, make_user, cookie_header):
    user = make_user(is_active=False)

    assert_unauthenticated(client.get(PROTECTED, headers=cookie_header(user)))


def test_every_rejection_looks_identical(client, make_user, cookie_header):
    """No failure mode is distinguishable from the response (AUTH-7's reasoning).

    "Expired", "wrong signature", "no such user" and "deactivated" are all
    facts a caller without a session hasn't earned.
    """
    user = make_user()
    deactivated = make_user(is_active=False)
    stale = datetime.now(timezone.utc) - timedelta(hours=2)

    bodies = {
        client.get(PROTECTED).text,
        client.get(PROTECTED, headers=cookie_header(user, now=stale)).text,
        client.get(PROTECTED, headers=cookie_header(deactivated)).text,
        client.get(PROTECTED, headers={"Cookie": f"{ACCESS_COOKIE_NAME}=garbage"}).text,
    }

    assert len(bodies) == 1, f"401 bodies differ between failure modes: {bodies}"


# --- XC-6: authorization -----------------------------------------------------


def test_admin_route_rejects_a_user_role_token(client, make_user, cookie_header):
    user = make_user(role="user")

    response = client.get(ADMIN_ONLY, headers=cookie_header(user))

    assert response.status_code == 403
    body = response.json()
    assert "detail" not in body
    assert body["error"]["code"] == "FORBIDDEN"


def test_admin_route_admits_an_admin(client, make_user, cookie_header):
    admin = make_user(role="admin")

    response = client.get(ADMIN_ONLY, headers=cookie_header(admin))

    assert response.status_code == 200
    assert response.json() == {"id": str(admin.id), "role": "admin"}


def test_admin_satisfies_a_user_minimum_route(client, make_user, cookie_header):
    # XC-6 is a *minimum* role, so the higher role must pass a lower gate.
    admin = make_user(role="admin")

    assert client.get(USER_OR_ABOVE, headers=cookie_header(admin)).status_code == 200


def test_role_gate_returns_401_not_403_without_a_session(client):
    # `require_role` composes on `get_current_user`, so "who are you" is
    # answered before "may you" — 403 to an anonymous caller would be claiming
    # to know something about them.
    assert_unauthenticated(client.get(ADMIN_ONLY))


def test_role_comes_from_the_database_not_the_claim(client, make_user, cookie_header):
    user = make_user(role="user")
    # A token that claims admin for a row that says user. The claim is signed,
    # so this is not forgery — it is what a stale token looks like after a
    # demotion, and the fresher value has to win.
    escalating = create_access_token(user_id=user.id, role="admin")

    response = client.get(ADMIN_ONLY, headers=cookie_header(user, token=escalating))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_require_role_rejects_an_unknown_role_at_construction():
    # Fails when the route module is imported, not on the first request that
    # happens to hit the typo'd gate.
    with pytest.raises(ValueError, match="Unknown role"):
        require_role("superadmin")
