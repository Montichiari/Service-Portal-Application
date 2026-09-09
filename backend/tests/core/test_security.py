"""Unit tests for app/core/security.py (T-AUTH-1 acceptance criteria).

These cover the parts of the module that need no database: password hashing,
access-token encode/decode, the auth cookies, and refresh-token generation and
hashing. The refresh-token *storage* helpers (``issue_refresh_token``,
``find_refresh_token``) take a ``Session`` and are tested against real Postgres
in tests/db/test_refresh_token_store.py, where the DB fixtures live.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import Response
from jwt.utils import base64url_decode, base64url_encode

from app.config import settings
from app.core.security import (
    ACCESS_COOKIE_NAME,
    ACCESS_TOKEN_TTL,
    MAX_PASSWORD_BYTES,
    REFRESH_COOKIE_NAME,
    REFRESH_TOKEN_TTL,
    AccessTokenClaims,
    InvalidAccessTokenError,
    clear_auth_cookies,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    set_access_cookie,
    set_refresh_cookie,
    verify_password,
)

PASSWORD = "correct horse battery staple"


# --- Password hashing --------------------------------------------------------


def test_hashed_password_verifies():
    """AC 1, first half: a hashed password verifies correctly."""
    assert verify_password(PASSWORD, hash_password(PASSWORD)) is True


def test_wrong_password_fails_verification():
    """AC 1, second half: a wrong password fails verification."""
    password_hash = hash_password(PASSWORD)

    assert verify_password("not the password", password_hash) is False
    # Near-misses, not just an obviously different string.
    assert verify_password(PASSWORD.upper(), password_hash) is False
    assert verify_password(PASSWORD + " ", password_hash) is False
    assert verify_password("", password_hash) is False


def test_hash_is_salted_and_not_plaintext():
    """Two hashes of the same password differ, and neither echoes the input."""
    first = hash_password(PASSWORD)
    second = hash_password(PASSWORD)

    assert first != second
    assert PASSWORD not in first
    # Both still verify — the salt is carried inside the hash string.
    assert verify_password(PASSWORD, first)
    assert verify_password(PASSWORD, second)


def test_hash_password_rejects_over_length_password():
    """Over-length input raises rather than being silently truncated.

    bcrypt only consumes 72 bytes. Silent truncation would make every password
    sharing a 72-byte prefix interchangeable, so the limit is surfaced to the
    caller instead (T-AUTH-3's register schema turns it into a 422).
    """
    with pytest.raises(ValueError, match="72-byte limit"):
        hash_password("a" * (MAX_PASSWORD_BYTES + 1))


def test_verify_password_never_raises_on_bad_input():
    """A malformed stored hash or over-length candidate is a failed check, not a 500."""
    assert verify_password(PASSWORD, "not-a-real-hash") is False
    assert verify_password(PASSWORD, "") is False
    assert verify_password("a" * (MAX_PASSWORD_BYTES + 1), hash_password(PASSWORD)) is False


def test_multibyte_password_length_is_measured_in_bytes():
    """The 72-byte ceiling is bytes, not characters — a 3-byte-per-char password
    hits it at 24 characters."""
    within_limit = "é" * 36  # 72 bytes exactly
    assert verify_password(within_limit, hash_password(within_limit)) is True

    with pytest.raises(ValueError):
        hash_password("é" * 37)  # 74 bytes


# --- Access-token JWTs -------------------------------------------------------


def test_access_token_round_trips():
    """AC 2, first half: encode then decode yields the same claims."""
    user_id = uuid.uuid4()

    claims = decode_access_token(create_access_token(user_id=user_id, role="admin"))

    assert isinstance(claims, AccessTokenClaims)
    assert claims.user_id == user_id
    assert claims.role == "admin"
    # design.md §1 requires all five claims; jti is server-generated.
    assert uuid.UUID(hex=claims.jti)
    assert claims.expires_at - claims.issued_at == ACCESS_TOKEN_TTL


def test_access_token_carries_the_documented_claim_names():
    """The wire format matches design.md §1's claim shape, not just our dataclass."""
    user_id = uuid.uuid4()
    token = create_access_token(user_id=user_id, role="user")

    payload = jwt.decode(
        token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )

    assert set(payload) == {"sub", "role", "iat", "exp", "jti"}
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "user"


def test_each_access_token_gets_a_distinct_jti():
    user_id = uuid.uuid4()

    first = decode_access_token(create_access_token(user_id=user_id, role="user"))
    second = decode_access_token(create_access_token(user_id=user_id, role="user"))

    assert first.jti != second.jti


def test_expired_access_token_fails_decode():
    """AC 2, second half (expiry): a token past its `exp` is rejected."""
    issued = datetime.now(timezone.utc) - ACCESS_TOKEN_TTL - timedelta(minutes=1)
    expired = create_access_token(user_id=uuid.uuid4(), role="user", now=issued)

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(expired)


def test_tampered_access_token_fails_decode():
    """AC 2, second half (tampering): an edited payload breaks the signature.

    Models the realistic attack — a `user` token with `role` rewritten to
    `admin` — by re-encoding the payload as *valid* base64url JSON and keeping
    the original signature. Doing it this way matters: simply corrupting
    characters in the payload segment makes it unparseable, so the token would
    be rejected as malformed even by an implementation that never checked the
    signature at all, and the test would pass for the wrong reason.
    """
    header, payload, signature = create_access_token(
        user_id=uuid.uuid4(), role="user"
    ).split(".")
    claims = json.loads(base64url_decode(payload))
    claims["role"] = "admin"
    forged_payload = base64url_encode(json.dumps(claims).encode("utf-8")).decode("ascii")
    tampered = f"{header}.{forged_payload}.{signature}"

    # Guard the premise: the tampered token really is well-formed, so the only
    # thing that can reject it below is the signature check.
    assert jwt.decode(tampered, options={"verify_signature": False})["role"] == "admin"

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(tampered)


def test_token_signed_with_another_secret_fails_decode():
    """Privilege escalation attempt: an admin token minted with the wrong key."""
    forged = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "role": "admin",
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "exp": int((datetime.now(timezone.utc) + ACCESS_TOKEN_TTL).timestamp()),
            "jti": uuid.uuid4().hex,
        },
        # Wrong key, but a full-length one — a short key would make PyJWT warn
        # about key length and muddy what this test is actually asserting.
        "not-the-real-signing-secret-but-long-enough-to-not-warn",
        algorithm=settings.JWT_ALGORITHM,
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(forged)


def test_unsigned_alg_none_token_fails_decode():
    """`algorithms=` is pinned, so an `alg: none` token is never trusted."""
    unsigned = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "role": "admin",
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "exp": int((datetime.now(timezone.utc) + ACCESS_TOKEN_TTL).timestamp()),
            "jti": uuid.uuid4().hex,
        },
        key="",
        algorithm="none",
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(unsigned)


@pytest.mark.parametrize("missing", ["sub", "role", "iat", "exp", "jti"])
def test_token_missing_a_required_claim_fails_decode(missing):
    payload = {
        "sub": str(uuid.uuid4()),
        "role": "user",
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + ACCESS_TOKEN_TTL).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    del payload[missing]
    token = jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)


def test_token_with_non_uuid_sub_fails_decode():
    """Correctly signed but structurally wrong — still rejected, not returned raw."""
    token = jwt.encode(
        {
            "sub": "not-a-uuid",
            "role": "user",
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "exp": int((datetime.now(timezone.utc) + ACCESS_TOKEN_TTL).timestamp()),
            "jti": uuid.uuid4().hex,
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    with pytest.raises(InvalidAccessTokenError, match="not a valid UUID"):
        decode_access_token(token)


def test_garbage_string_fails_decode():
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token("this is not a jwt at all")


# --- Auth cookies ------------------------------------------------------------


def _set_cookie_header(response: Response, name: str) -> str:
    headers = [
        value
        for key, value in response.raw_headers
        if key == b"set-cookie" and value.decode().startswith(f"{name}=")
    ]
    assert len(headers) == 1, f"expected exactly one {name} cookie, got {headers}"
    return headers[0].decode()


def test_access_cookie_attributes_match_the_contract():
    """AUTH-6: httpOnly, Secure, SameSite=Lax, 1 hour."""
    response = Response()

    set_access_cookie(response, "a-token")

    header = _set_cookie_header(response, ACCESS_COOKIE_NAME)
    assert "a-token" in header
    assert "HttpOnly" in header
    assert "Secure" in header
    assert "SameSite=lax" in header
    assert f"Max-Age={int(ACCESS_TOKEN_TTL.total_seconds())}" in header
    assert int(ACCESS_TOKEN_TTL.total_seconds()) == 3600


def test_refresh_cookie_attributes_match_the_contract():
    """AUTH-6: same attributes, 30 day lifetime."""
    response = Response()

    set_refresh_cookie(response, "a-raw-refresh-token")

    header = _set_cookie_header(response, REFRESH_COOKIE_NAME)
    assert "HttpOnly" in header
    assert "Secure" in header
    assert "SameSite=lax" in header
    assert f"Max-Age={int(REFRESH_TOKEN_TTL.total_seconds())}" in header
    assert int(REFRESH_TOKEN_TTL.total_seconds()) == 30 * 24 * 60 * 60


def test_clear_auth_cookies_expires_both():
    """AUTH-12's clearing half — both cookies expired, attributes preserved so
    the browser matches them to the originals."""
    response = Response()

    clear_auth_cookies(response)

    for name in (ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME):
        header = _set_cookie_header(response, name)
        assert "Max-Age=0" in header
        assert "HttpOnly" in header
        assert "Secure" in header
        assert "SameSite=lax" in header


# --- Refresh-token generation and hashing ------------------------------------


def test_refresh_tokens_are_unique_and_high_entropy():
    tokens = {generate_refresh_token() for _ in range(100)}

    assert len(tokens) == 100
    # 32 random bytes, URL-safe base64 → 43 chars.
    assert all(len(token) >= 43 for token in tokens)


def test_refresh_token_hash_is_stable_and_not_the_raw_token():
    raw = generate_refresh_token()

    hashed = hash_refresh_token(raw)

    assert hashed == hash_refresh_token(raw)  # deterministic — required for lookup
    assert hashed != raw
    assert raw not in hashed
    assert len(hashed) == 64  # sha256 hex
    # Comfortably inside refresh_tokens.token_hash's VARCHAR(255).
    assert len(hashed) <= 255


def test_different_refresh_tokens_hash_differently():
    assert hash_refresh_token(generate_refresh_token()) != hash_refresh_token(
        generate_refresh_token()
    )
