"""The five auth endpoints (T-AUTH-3; AUTH-1 .. AUTH-16, XC-13, XC-15).

Contract tests against the real Postgres test database and the real
``create_app()`` (backend/CLAUDE.md) — no SQLite, no hand-assembled app.

Error assertions check the whole envelope, not the status code alone: a 422
carrying the wrong ``fields`` key is still a broken contract even though the
number is right.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_current_user
from app.core.security import (
    ACCESS_COOKIE_NAME,
    MAX_PASSWORD_BYTES,
    REFRESH_COOKIE_NAME,
    create_access_token,
    hash_password,
    hash_refresh_token,
)
from app.db.models import RefreshToken, User

AUTH = "/api/v1/auth"
REGISTER = f"{AUTH}/register"
LOGIN = f"{AUTH}/login"
ME = f"{AUTH}/me"
REFRESH = f"{AUTH}/refresh"
LOGOUT = f"{AUTH}/logout"

# 28 characters, no digit, no symbol, no uppercase — a deliberate reminder
# that AUTH-3's rule is length and nothing else.
PASSWORD = "correct horse battery staple"

# AUTH-6's lifetimes, written out rather than imported from
# `app.core.security`. Deriving them from `ACCESS_TOKEN_TTL` /
# `REFRESH_TOKEN_TTL` reads more DRY and asserts nothing: the expected value
# would move with the constant under test, so changing the access token to
# last 30 days would keep the test green. (Found by this task's mutation pass,
# which is the only way a test like that ever gets noticed.) A deliberate
# lifetime change is therefore a two-line diff — the constant and this pin —
# which is the right cost for editing a contract.
ACCESS_COOKIE_MAX_AGE = 60 * 60  # 1 hour
REFRESH_COOKIE_MAX_AGE = 30 * 24 * 60 * 60  # 30 days


# --- helpers -----------------------------------------------------------------


def replace_cookie(client: TestClient, name: str, value: str) -> None:
    """Overwrite one cookie in the jar, keeping the jar's own scoping.

    ``Cookies.set`` defaults to an empty domain, while ``http.cookiejar`` files
    a server-set cookie under the effective request host — ``testserver.local``
    for this client. Those are different keys, so a bare ``set`` adds a second
    entry rather than replacing the first: both get sent, the server reads
    whichever it parses last, and the test fails looking exactly like a
    rejected token rather than like a cookie-jar problem. Copying the existing
    entry's domain and path is what makes it an overwrite.
    """
    existing = next(cookie for cookie in client.cookies.jar if cookie.name == name)
    client.cookies.set(name, value, domain=existing.domain, path=existing.path)


def registration(**overrides: object) -> dict[str, object]:
    """A valid register body, with a unique email unless one is given.

    ``@example.com``, not the ``@example.test`` the database fixtures use:
    ``.test`` is an IANA special-use TLD and ``email-validator`` — which backs
    the schema's ``EmailStr`` — refuses it. The row factories never cross that
    validator, so both conventions are correct in their own place.
    """
    payload: dict[str, object] = {
        "first_name": "Daniel",
        "last_name": "Osei",
        "email": f"daniel-{uuid.uuid4().hex[:12]}@example.com",
        "password": PASSWORD,
    }
    payload.update(overrides)
    return payload


def set_cookies(response) -> dict[str, str]:
    """Every ``Set-Cookie`` line on a response, keyed by cookie name."""
    return {
        line.split("=", 1)[0].strip(): line
        for line in response.headers.get_list("set-cookie")
    }


def assert_cookie_attributes(line: str, *, max_age: int) -> None:
    """AUTH-6's attributes, read off the raw header rather than a parsed jar.

    A cookie jar normalises away exactly the attributes under test — a jar can
    hold a cookie that was never marked ``Secure``.
    """
    lowered = line.lower()
    assert "httponly" in lowered, line
    assert "secure" in lowered, line
    assert "samesite=lax" in lowered, line
    assert "path=/" in lowered, line
    assert f"max-age={max_age}" in lowered, line


def assert_envelope(response, status_code: int, code: str) -> dict:
    assert response.status_code == status_code, response.text
    body = response.json()
    assert "detail" not in body, "FastAPI's default shape leaked through"
    assert set(body) == {"error"}
    error = body["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]
    return error


def register_and_login(client: TestClient, **overrides: object) -> dict[str, object]:
    """Run the real register -> login sequence; return the register body used."""
    payload = registration(**overrides)
    assert client.post(REGISTER, json=payload).status_code == 201
    assert (
        client.post(
            LOGIN, json={"email": payload["email"], "password": payload["password"]}
        ).status_code
        == 200
    )
    return payload


def stored_user(db_session, email: str) -> User:
    return db_session.execute(
        select(User).where(User.email == email.lower())
    ).scalar_one()


# --- AUTH-1: register succeeds -----------------------------------------------


def test_register_creates_a_user_row_and_returns_201(auth_client, db_session):
    payload = registration()

    response = auth_client.post(REGISTER, json=payload)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "first_name", "last_name", "email", "role", "created_at"}
    assert body["first_name"] == "Daniel"
    assert body["email"] == payload["email"]
    assert body["role"] == "user"

    user = stored_user(db_session, str(payload["email"]))
    assert str(user.id) == body["id"]
    assert user.role == "user"
    assert user.is_active is True
    # Stored hashed, never in plaintext.
    assert user.password_hash != PASSWORD


def test_register_sets_no_cookies(auth_client):
    response = auth_client.post(REGISTER, json=registration())

    # AUTH-1: registering is not signing in. A cookie here would make this
    # endpoint a way to mint a session without ever proving a password.
    assert response.status_code == 201
    assert response.headers.get_list("set-cookie") == []


def test_register_timestamp_is_iso_8601_utc(auth_client):
    # XC-2. The `Z` matters: an offsetless string is read as local time by
    # every browser that parses it.
    created_at = auth_client.post(REGISTER, json=registration()).json()["created_at"]

    assert created_at.endswith("Z"), created_at
    parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert abs((datetime.now(timezone.utc) - parsed).total_seconds()) < 60


# --- AUTH-2: duplicate email --------------------------------------------------


def test_duplicate_email_returns_409(auth_client):
    payload = registration()
    assert auth_client.post(REGISTER, json=payload).status_code == 201

    error = assert_envelope(auth_client.post(REGISTER, json=payload), 409, "CONFLICT")

    # design.md §1 reserves `fields` for VALIDATION_ERROR, and AUTH-2 caps what
    # may be revealed at "this email is taken" — so no other user data either.
    assert "fields" not in error
    assert "email" in error["message"].lower()


def test_duplicate_email_ignores_case(auth_client, db_session):
    payload = registration(email="Ada.Lovelace@example.com")
    assert auth_client.post(REGISTER, json=payload).status_code == 201

    upper = auth_client.post(REGISTER, json=registration(email="ADA.LOVELACE@example.com"))

    # Postgres' unique index compares exactly, so without normalisation these
    # would be two accounts and the second one's owner would find their
    # password "wrong" whenever they capitalised their address.
    assert_envelope(upper, 409, "CONFLICT")
    assert (
        db_session.execute(
            select(User).where(User.email == "ada.lovelace@example.com")
        ).scalar_one()
    )


def test_a_race_past_the_pre_check_still_conflicts(auth_client, monkeypatch):
    """The unique index, not the SELECT, is what actually decides (AUTH-2).

    Simulates the interleaving where another registration for the same address
    commits between this one's check and its INSERT, by making the check always
    say "free". The caller must not be able to tell the difference.
    """
    payload = registration()
    assert auth_client.post(REGISTER, json=payload).status_code == 201

    monkeypatch.setattr("app.api.routes.auth._email_taken", lambda db, email: False)

    assert_envelope(auth_client.post(REGISTER, json=payload), 409, "CONFLICT")


# --- AUTH-4: role is not client-supplied --------------------------------------


def test_a_role_field_in_the_register_body_is_ignored(auth_client, db_session):
    payload = registration(email="climber@example.com")

    response = auth_client.post(REGISTER, json={**payload, "role": "admin"})

    # XC-8: ignored, not rejected — the request succeeds, it just doesn't get
    # what it asked for. Checked in the database as well as the body, since a
    # response model would hide a stored 'admin' behind a filtered field.
    assert response.status_code == 201
    assert response.json()["role"] == "user"
    assert stored_user(db_session, "climber@example.com").role == "user"


# --- AUTH-3: password length policy -------------------------------------------


def test_an_11_character_password_is_rejected(auth_client):
    response = auth_client.post(REGISTER, json=registration(password="a" * 11))

    error = assert_envelope(response, 422, "VALIDATION_ERROR")
    assert list(error["fields"]) == ["password"]


def test_a_12_character_all_lowercase_password_is_accepted(auth_client):
    # No digit, no symbol, no uppercase. AUTH-3 is length-only by decision, so
    # this succeeding is the requirement — not an oversight to tighten later.
    response = auth_client.post(REGISTER, json=registration(password="abcdefghijkl"))

    assert response.status_code == 201


# --- AUTH-16: bcrypt's 72-byte ceiling ----------------------------------------


def test_a_password_over_72_bytes_is_rejected(auth_client):
    response = auth_client.post(
        REGISTER, json=registration(password="a" * (MAX_PASSWORD_BYTES + 1))
    )

    # 422, not 500: `hash_password` raises on over-long input, so without the
    # schema check this would be an unhandled exception.
    error = assert_envelope(response, 422, "VALIDATION_ERROR")
    assert list(error["fields"]) == ["password"]


def test_a_password_under_72_characters_but_over_72_bytes_is_rejected(auth_client):
    # 30 emoji: 30 characters, 120 bytes. A `max_length` constraint counts
    # characters and would wave this through to a 500 at the hasher.
    password = "🔒" * 30
    assert len(password) < MAX_PASSWORD_BYTES < len(password.encode("utf-8"))

    response = auth_client.post(REGISTER, json=registration(password=password))

    error = assert_envelope(response, 422, "VALIDATION_ERROR")
    assert list(error["fields"]) == ["password"]


def test_a_password_of_exactly_72_bytes_is_accepted(auth_client):
    # The boundary belongs to the caller: bcrypt hashes 72 bytes, so 72 is
    # valid and 73 is not.
    response = auth_client.post(
        REGISTER, json=registration(password="a" * MAX_PASSWORD_BYTES)
    )

    assert response.status_code == 201


# --- AUTH-5 / XC-15: password material never appears in a body ----------------


def test_no_success_response_contains_password_material(auth_client, db_session):
    payload = register_and_login(auth_client)
    user = stored_user(db_session, str(payload["email"]))

    for response in (
        auth_client.post(REGISTER, json=registration()),
        auth_client.post(
            LOGIN, json={"email": payload["email"], "password": payload["password"]}
        ),
        auth_client.get(ME),
    ):
        assert "password" not in response.text.lower(), response.text
        assert user.password_hash not in response.text


def test_a_rejected_password_is_not_echoed_back(auth_client):
    # A validation error carries Pydantic's `msg` and nothing else; copying the
    # whole error dict would put the rejected input — here, the password — into
    # the response body.
    secret = "short🔒" * 20

    response = auth_client.post(REGISTER, json=registration(password=secret))

    assert response.status_code == 422
    assert secret not in response.text


def test_a_serialization_failure_on_me_never_leaks_the_password_hash(
    api_app, caplog: pytest.LogCaptureFixture
):
    """XC-15 — the leak path no success-path test touches.

    ``response_model`` filtering and error handling are one security boundary.
    When serialization against the model fails, FastAPI's
    ``ResponseValidationError`` carries the offending value in its own message,
    and that value is precisely the field the model existed to exclude. A 500
    handler rendering ``str(exc)`` would turn AUTH-5's "ever" into a live leak.

    ``/auth/me`` is picked because a ``User`` row is its serialization source.
    The override supplies a user-shaped object missing ``role``, so the model
    fails and reports the whole object as the offending input.
    """
    leak = "$2b$12$serialization-leak-hunter2"

    class _UserMissingRole:
        id = uuid.uuid4()
        first_name = "Ada"
        last_name = "Lovelace"
        password_hash = leak

        def __repr__(self) -> str:
            return f"<User password_hash={leak!r}>"

    api_app.dependency_overrides[get_current_user] = lambda: _UserMissingRole()

    with TestClient(
        api_app, base_url="https://testserver", raise_server_exceptions=False
    ) as client:
        with caplog.at_level(logging.ERROR, logger="app.api.errors"):
            response = client.get(ME)

    assert_envelope(response, 500, "INTERNAL_ERROR")
    assert leak not in response.text
    # Non-vacuous: the value really did reach the exception, it just never
    # reached the body. Without this the test would keep passing if the
    # response model stopped failing at all, which would prove nothing.
    assert leak in caplog.text


# --- AUTH-6: login succeeds ---------------------------------------------------


def test_login_sets_both_cookies_with_the_right_attributes(auth_client):
    payload = registration()
    auth_client.post(REGISTER, json=payload)

    response = auth_client.post(
        LOGIN, json={"email": payload["email"], "password": payload["password"]}
    )

    assert response.status_code == 200
    cookies = set_cookies(response)
    assert set(cookies) == {ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME}
    assert_cookie_attributes(cookies[ACCESS_COOKIE_NAME], max_age=ACCESS_COOKIE_MAX_AGE)
    assert_cookie_attributes(
        cookies[REFRESH_COOKIE_NAME], max_age=REFRESH_COOKIE_MAX_AGE
    )


def test_login_returns_the_session_shape(auth_client, db_session):
    payload = registration()
    auth_client.post(REGISTER, json=payload)

    body = auth_client.post(
        LOGIN, json={"email": payload["email"], "password": payload["password"]}
    ).json()

    # design.md §2: id, first_name, last_name, role — no email, no timestamps.
    assert set(body) == {"id", "first_name", "last_name", "role"}
    assert body["id"] == str(stored_user(db_session, str(payload["email"])).id)


def test_login_stores_only_the_refresh_token_hash(auth_client, db_session):
    payload = register_and_login(auth_client)
    raw = auth_client.cookies.get(REFRESH_COOKIE_NAME)

    user = stored_user(db_session, str(payload["email"]))
    rows = db_session.execute(
        select(RefreshToken).where(RefreshToken.user_id == user.id)
    ).scalars().all()

    assert len(rows) == 1
    assert rows[0].token_hash == hash_refresh_token(raw)
    assert rows[0].token_hash != raw


def test_login_ignores_email_case(auth_client):
    payload = registration(email="grace.hopper@example.com")
    auth_client.post(REGISTER, json=payload)

    response = auth_client.post(
        LOGIN, json={"email": "Grace.Hopper@EXAMPLE.COM", "password": PASSWORD}
    )

    assert response.status_code == 200


# --- AUTH-7 / AUTH-8: login failures are indistinguishable --------------------


def test_wrong_email_and_wrong_password_are_byte_identical(auth_client):
    payload = registration()
    auth_client.post(REGISTER, json=payload)

    wrong_password = auth_client.post(
        LOGIN, json={"email": payload["email"], "password": "not-the-password"}
    )
    unknown_email = auth_client.post(
        LOGIN, json={"email": "nobody-here@example.com", "password": PASSWORD}
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    # Byte-identical, not merely "both 401": a difference in wording is the
    # user-enumeration leak AUTH-7 exists to close.
    assert wrong_password.text == unknown_email.text
    error = assert_envelope(wrong_password, 401, "UNAUTHENTICATED")
    assert error["message"] == "Incorrect email or password."
    assert wrong_password.headers.get_list("set-cookie") == []


def test_a_deactivated_user_gets_the_same_failure(auth_client, db_session):
    payload = registration()
    auth_client.post(REGISTER, json=payload)
    user = stored_user(db_session, str(payload["email"]))
    user.is_active = False
    db_session.commit()

    deactivated = auth_client.post(
        LOGIN, json={"email": payload["email"], "password": payload["password"]}
    )
    unknown_email = auth_client.post(
        LOGIN, json={"email": "nobody-here@example.com", "password": PASSWORD}
    )

    # AUTH-8: no "account disabled" message — same non-enumeration reasoning.
    assert deactivated.status_code == 401
    assert deactivated.text == unknown_email.text


# --- AUTH-14 / AUTH-15: /auth/me ---------------------------------------------


def test_me_returns_the_signed_in_user(auth_client, db_session):
    payload = register_and_login(auth_client)

    response = auth_client.get(ME)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "first_name", "last_name", "role"}
    assert body["id"] == str(stored_user(db_session, str(payload["email"])).id)
    assert body["first_name"] == "Daniel"


def test_me_without_a_cookie_is_401(auth_client):
    assert_envelope(auth_client.get(ME), 401, "UNAUTHENTICATED")


def test_me_does_not_fall_back_to_the_refresh_cookie(auth_client):
    """AUTH-15 — an expired access token is a 401 here, not a silent refresh."""
    register_and_login(auth_client)
    refresh_cookie = auth_client.cookies.get(REFRESH_COOKIE_NAME)
    # Drop only the access cookie; the refresh cookie stays valid. If `/me`
    # quietly refreshed, an expired session would be indistinguishable from a
    # live one and the frontend could never tell it needed to re-authenticate.
    auth_client.cookies.delete(ACCESS_COOKIE_NAME)

    response = auth_client.get(ME)

    assert auth_client.cookies.get(REFRESH_COOKIE_NAME) == refresh_cookie
    assert_envelope(response, 401, "UNAUTHENTICATED")
    assert response.headers.get_list("set-cookie") == []


# --- XC-13: the database is the source of truth on every request --------------


def test_deactivation_takes_effect_on_the_very_next_request(auth_client, db_session):
    payload = register_and_login(auth_client)
    assert auth_client.get(ME).status_code == 200

    user = stored_user(db_session, str(payload["email"]))
    user.is_active = False
    db_session.commit()

    # The access token is still validly signed and nowhere near its 1-hour
    # expiry. Trusting the claims alone would leave this session working for up
    # to another hour after the account was switched off.
    assert_envelope(auth_client.get(ME), 401, "UNAUTHENTICATED")


# --- AUTH-9 / AUTH-10 / AUTH-11: refresh --------------------------------------


def test_refresh_rotates_the_token_and_reissues_cookies(auth_client, db_session):
    payload = register_and_login(auth_client)
    user = stored_user(db_session, str(payload["email"]))
    old_raw = auth_client.cookies.get(REFRESH_COOKIE_NAME)

    response = auth_client.post(REFRESH)

    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)

    cookies = set_cookies(response)
    assert set(cookies) == {ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME}
    assert_cookie_attributes(cookies[ACCESS_COOKIE_NAME], max_age=ACCESS_COOKIE_MAX_AGE)
    assert_cookie_attributes(
        cookies[REFRESH_COOKIE_NAME], max_age=REFRESH_COOKIE_MAX_AGE
    )

    rows = db_session.execute(
        select(RefreshToken).where(RefreshToken.user_id == user.id)
    ).scalars().all()
    by_hash = {row.token_hash: row for row in rows}
    # Single-use rotation: the presented row is revoked and a replacement
    # inserted, rather than the same token staying live for 30 days.
    assert len(rows) == 2
    assert by_hash[hash_refresh_token(old_raw)].revoked_at is not None
    new_raw = auth_client.cookies.get(REFRESH_COOKIE_NAME)
    assert new_raw != old_raw
    assert by_hash[hash_refresh_token(new_raw)].revoked_at is None


def test_refresh_without_a_cookie_is_401(auth_client):
    response = auth_client.post(REFRESH)

    assert_envelope(response, 401, "UNAUTHENTICATED")
    assert response.headers.get_list("set-cookie") == []


def test_refresh_with_an_unknown_token_is_401(auth_client):
    auth_client.cookies.set(REFRESH_COOKIE_NAME, "never-issued-by-anyone")

    response = auth_client.post(REFRESH)

    assert_envelope(response, 401, "UNAUTHENTICATED")
    assert response.headers.get_list("set-cookie") == []


def test_refresh_with_an_expired_token_is_401(auth_client, db_session, make_user):
    user = make_user()
    raw = "expired-but-genuinely-issued"
    db_session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw),
            # Unrevoked, just old. AUTH-10 covers expiry separately from
            # revocation, and this path must not trigger AUTH-11's family
            # revocation — an old session is not a theft signal.
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
    )
    db_session.commit()
    auth_client.cookies.set(REFRESH_COOKIE_NAME, raw)

    response = auth_client.post(REFRESH)

    assert_envelope(response, 401, "UNAUTHENTICATED")
    assert response.headers.get_list("set-cookie") == []


def test_replaying_a_rotated_token_revokes_the_whole_family(auth_client, db_session):
    """AUTH-11 — a token that came back after rotation burns its siblings."""
    payload = register_and_login(auth_client)
    user = stored_user(db_session, str(payload["email"]))
    stolen = auth_client.cookies.get(REFRESH_COOKIE_NAME)

    assert auth_client.post(REFRESH).status_code == 200
    live_after_rotation = auth_client.cookies.get(REFRESH_COOKIE_NAME)
    assert live_after_rotation != stolen

    # The legitimate holder rotated; this is the copy someone else kept.
    auth_client.cookies.clear()
    auth_client.cookies.set(REFRESH_COOKIE_NAME, stolen)
    replay = auth_client.post(REFRESH)

    assert_envelope(replay, 401, "UNAUTHENTICATED")
    assert replay.headers.get_list("set-cookie") == []

    db_session.expire_all()
    rows = db_session.execute(
        select(RefreshToken).where(RefreshToken.user_id == user.id)
    ).scalars().all()
    # Every one, including the currently-live token the real user is holding:
    # once a rotated token reappears, the two can no longer be told apart.
    assert len(rows) == 2
    assert all(row.revoked_at is not None for row in rows)

    auth_client.cookies.clear()
    auth_client.cookies.set(REFRESH_COOKIE_NAME, live_after_rotation)
    assert auth_client.post(REFRESH).status_code == 401


# --- AUTH-12 / AUTH-13: logout ------------------------------------------------


def test_logout_revokes_the_token_and_clears_both_cookies(auth_client, db_session):
    payload = register_and_login(auth_client)
    user = stored_user(db_session, str(payload["email"]))
    raw = auth_client.cookies.get(REFRESH_COOKIE_NAME)

    response = auth_client.post(LOGOUT)

    assert response.status_code == 204
    assert response.content == b""

    cookies = set_cookies(response)
    assert set(cookies) == {ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME}
    for line in cookies.values():
        lowered = line.lower()
        # The clearing cookie has to carry the same attributes as the one it
        # replaces, or the browser treats it as a different cookie and the
        # original survives.
        assert "httponly" in lowered and "secure" in lowered
        assert "samesite=lax" in lowered and "path=/" in lowered
        assert "max-age=0" in lowered or "expires=" in lowered

    db_session.expire_all()
    row = db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw))
    ).scalar_one()
    assert row.revoked_at is not None
    assert row.user_id == user.id


def test_logout_without_a_session_is_still_204(auth_client):
    # AUTH-13. A 401 here would fail a user's "sign out" click at the one
    # moment it is least worth arguing about — when their session had already
    # expired — and leave the stale cookies in place.
    response = auth_client.post(LOGOUT)

    assert response.status_code == 204
    assert set(set_cookies(response)) == {ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME}


def test_logout_is_idempotent(auth_client):
    register_and_login(auth_client)

    assert auth_client.post(LOGOUT).status_code == 204
    assert auth_client.post(LOGOUT).status_code == 204


def test_logout_ends_the_session_for_real(auth_client):
    register_and_login(auth_client)
    auth_client.post(LOGOUT)

    # The cookies were cleared client-side *and* the refresh token revoked, so
    # neither call can be resurrected.
    assert auth_client.get(ME).status_code == 401
    assert auth_client.post(REFRESH).status_code == 401


# --- the flow as a whole ------------------------------------------------------


def test_register_then_login_then_authenticated_call(auth_client):
    """The sequence T-AUTH-4's client will actually perform."""
    payload = registration()

    assert auth_client.post(REGISTER, json=payload).status_code == 201
    # Registration set no session, so /me is 401 until a real login happens.
    assert auth_client.get(ME).status_code == 401

    login = auth_client.post(
        LOGIN, json={"email": payload["email"], "password": payload["password"]}
    )
    assert login.status_code == 200

    me = auth_client.get(ME)
    assert me.status_code == 200
    assert me.json() == login.json()


def test_a_stale_access_token_recovers_through_refresh(auth_client, db_session):
    """Access expired, refresh still good — the case /auth/refresh exists for."""
    payload = registration()
    auth_client.post(REGISTER, json=payload)
    auth_client.post(
        LOGIN, json={"email": payload["email"], "password": payload["password"]}
    )

    # Simulate the hour passing by replacing the access cookie with one issued
    # two hours ago, leaving the refresh cookie untouched.
    user = stored_user(db_session, str(payload["email"]))
    stale = create_access_token(
        user_id=user.id,
        role=user.role,
        now=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    replace_cookie(auth_client, ACCESS_COOKIE_NAME, stale)
    assert auth_client.get(ME).status_code == 401

    assert auth_client.post(REFRESH).status_code == 200
    assert auth_client.get(ME).status_code == 200


def test_the_csrf_check_still_applies_to_the_real_auth_routes(client):
    # `auth_client` sends X-Requested-With by default, which would mask a
    # regression in XC-9 on exactly the endpoints that change state. The plain
    # client sends none.
    for path in (REGISTER, LOGIN, REFRESH, LOGOUT):
        assert_envelope(client.post(path, json={}), 403, "FORBIDDEN")


def test_password_hashes_are_salted_per_user(auth_client, db_session):
    """Two identical passwords must not produce the same stored hash."""
    first, second = registration(), registration()
    auth_client.post(REGISTER, json=first)
    auth_client.post(REGISTER, json=second)

    hashes = {
        stored_user(db_session, str(first["email"])).password_hash,
        stored_user(db_session, str(second["email"])).password_hash,
    }

    assert len(hashes) == 2
    assert all(h != hash_password(PASSWORD) for h in hashes)
