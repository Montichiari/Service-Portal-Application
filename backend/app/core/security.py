"""Auth primitives — password hashing, access-token JWTs, auth cookies and
refresh-token storage (T-AUTH-1; specs/api-phase/design.md §1-§2).

This module is the single home for every cryptographic and cookie decision in
the API (backend/CLAUDE.md): route code imports these helpers and never calls
``bcrypt``, ``jwt`` or ``response.set_cookie`` directly. Token lifetimes and
cookie attributes are the module constants below, so changing one is a
one-line diff rather than a grep across route files.

Nothing here defines a route. T-AUTH-2 builds the dependencies that consume
these helpers; T-AUTH-3 builds the endpoints.

**Hashing backend**: ``bcrypt`` directly, not ``passlib[bcrypt]``. passlib's
last release (1.7.4, 2020) probes its bcrypt backend by hashing an
over-length secret to detect an old wraparound bug; bcrypt >= 4.1 raises on
over-length input instead of truncating, so that probe fails and *every*
``CryptContext.hash()`` call raises ``ValueError``. Verified broken against
bcrypt 5.0.0 on this project's interpreter — not a theoretical concern.
tasks.md's T-AUTH-1 scope allows "passlib[bcrypt] or equivalent"; this is the
equivalent.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import RefreshToken

# --- Lifetimes ---------------------------------------------------------------
# design.md §1 ("Lifetimes"): 1 hour access / 30 day refresh. Defined here and
# only here — deliberately not in Settings, because these are contract
# decisions from the design document, not per-environment configuration. (The
# skeleton phase's placeholder ACCESS_TOKEN_EXPIRE_MINUTES=30 setting
# contradicted the design's 1 hour and was removed in this task rather than
# left as a second, wrong source of truth.)

ACCESS_TOKEN_TTL = timedelta(hours=1)
REFRESH_TOKEN_TTL = timedelta(days=30)


# --- Password hashing --------------------------------------------------------

# bcrypt hashes at most 72 bytes of input. bcrypt >= 4.1 raises on anything
# longer rather than silently truncating — which is the safer behaviour, since
# silent truncation makes two different long passwords interchangeable. This
# limit is exported so T-AUTH-3's register schema can reject over-long
# passwords with a 422 (per XC-4) instead of letting them reach the hasher.
MAX_PASSWORD_BYTES = 72

# bcrypt's own default cost. Raising it is a one-line change here; existing
# hashes stay verifiable because the cost is encoded in the hash string.
BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    """Hash a plaintext password for storage in ``users.password_hash``.

    Raises ``ValueError`` if the password exceeds ``MAX_PASSWORD_BYTES`` when
    UTF-8 encoded — callers validate length first (see ``MAX_PASSWORD_BYTES``).
    """
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password exceeds bcrypt's {MAX_PASSWORD_BYTES}-byte limit "
            f"({len(encoded)} bytes)."
        )
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode(
        "utf-8"
    )


def verify_password(password: str, password_hash: str) -> bool:
    """Check a plaintext password against a stored hash.

    Always returns a bool — never raises. A malformed stored hash or an
    over-length candidate password is a failed check, not a 500: an
    over-length password can never have been stored by ``hash_password``, so
    it can never legitimately match.
    """
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
    except ValueError:
        return False


# --- Access-token JWTs -------------------------------------------------------


class InvalidAccessTokenError(Exception):
    """An access token is missing, malformed, expired, or tampered with.

    Raised instead of leaking PyJWT's exception types to callers, so T-AUTH-2's
    ``get_current_user`` can map a single exception type onto the
    ``401``/``UNAUTHENTICATED`` envelope (XC-5) without importing ``jwt``.
    """


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    """The decoded, validated contents of an access token (design.md §1)."""

    user_id: uuid.UUID  # the token's `sub` claim
    role: str
    jti: str
    issued_at: datetime
    expires_at: datetime


def create_access_token(
    *,
    user_id: uuid.UUID,
    role: str,
    now: datetime | None = None,
) -> str:
    """Encode a signed access token for ``user_id``.

    ``role`` is embedded so authorization needs no DB round-trip per request —
    with the documented tradeoff (design.md §1) that a role change only takes
    effect once a new token is issued.

    ``now`` is injectable so tests can mint deliberately-expired tokens
    without sleeping; production callers omit it.
    """
    now = now or datetime.now(timezone.utc)
    expires_at = now + ACCESS_TOKEN_TTL
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        # Per-token id, for log correlation and future revocation (design.md
        # §1). Not currently checked against a denylist.
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def decode_access_token(token: str) -> AccessTokenClaims:
    """Verify and decode an access token.

    Raises ``InvalidAccessTokenError`` for a bad signature, an expired ``exp``,
    a missing required claim, or a ``sub`` that isn't a UUID.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            # Pinning the accepted algorithm is what stops a caller supplying a
            # token with `alg: none` (or an asymmetric-to-HMAC confusion) and
            # having it verified. Never widen this to the token's own header.
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "role", "iat", "exp", "jti"]},
        )
    except jwt.InvalidTokenError as exc:
        # ExpiredSignatureError, InvalidSignatureError, MissingRequiredClaimError
        # and friends all subclass InvalidTokenError.
        raise InvalidAccessTokenError(str(exc)) from exc

    try:
        user_id = uuid.UUID(payload["sub"])
    except (AttributeError, TypeError, ValueError) as exc:
        raise InvalidAccessTokenError("`sub` claim is not a valid UUID") from exc

    return AccessTokenClaims(
        user_id=user_id,
        role=payload["role"],
        jti=payload["jti"],
        issued_at=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
        expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
    )


# --- Auth cookies ------------------------------------------------------------

ACCESS_COOKIE_NAME = "access_token"
REFRESH_COOKIE_NAME = "refresh_token"

# design.md §1 / AUTH-6. `Secure` is unconditional rather than an environment
# toggle: browsers treat http://localhost as a trustworthy origin, so Secure
# cookies are still set during local development over plain HTTP. (The
# skeleton phase's COOKIE_SECURE=false placeholder would have shipped
# non-Secure cookies in violation of AUTH-6; it was removed in this task.)
COOKIE_HTTPONLY = True
COOKIE_SECURE = True
COOKIE_SAMESITE = "lax"
# Both cookies are site-wide. Scoping the refresh cookie to /auth/refresh would
# be tighter, but AUTH-12's logout also needs to read it, and logout lives at a
# different path.
COOKIE_PATH = "/"


def _set_auth_cookie(
    response: Response, name: str, value: str, ttl: timedelta
) -> None:
    response.set_cookie(
        key=name,
        value=value,
        max_age=int(ttl.total_seconds()),
        httponly=COOKIE_HTTPONLY,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
    )


def set_access_cookie(response: Response, token: str) -> None:
    """Attach the access-token cookie (1 hour, AUTH-6)."""
    _set_auth_cookie(response, ACCESS_COOKIE_NAME, token, ACCESS_TOKEN_TTL)


def set_refresh_cookie(response: Response, raw_token: str) -> None:
    """Attach the refresh-token cookie (30 days, AUTH-6).

    Takes the *raw* token — only its hash is ever persisted, see
    ``issue_refresh_token``.
    """
    _set_auth_cookie(response, REFRESH_COOKIE_NAME, raw_token, REFRESH_TOKEN_TTL)


def clear_auth_cookies(response: Response) -> None:
    """Expire both auth cookies immediately (AUTH-12).

    The attributes must match those used when setting the cookies, or the
    browser treats the deletion as targeting a different cookie and the
    original survives.
    """
    for name in (ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME):
        response.delete_cookie(
            key=name,
            httponly=COOKIE_HTTPONLY,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,
            path=COOKIE_PATH,
        )


# --- Refresh tokens ----------------------------------------------------------

# 32 bytes = 256 bits of entropy, URL-safe base64 encoded.
REFRESH_TOKEN_BYTES = 32


def generate_refresh_token() -> str:
    """A fresh opaque refresh token (design.md §1 — opaque, not a JWT)."""
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(raw_token: str) -> str:
    """Hash a raw refresh token for storage in ``refresh_tokens.token_hash``.

    SHA-256 rather than bcrypt, for two reasons. First, lookup: ``token_hash``
    is indexed and looked up by exact match, and a salted bcrypt hash can only
    be checked by scanning every row and verifying each in turn. Second, a slow
    KDF buys nothing here — bcrypt protects low-entropy human-chosen
    passwords, whereas these tokens are 256 bits of CSPRNG output and are not
    guessable at any hash speed.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_refresh_token(
    db: Session,
    user_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> tuple[str, RefreshToken]:
    """Mint a refresh token for ``user_id``, persisting only its hash.

    Returns ``(raw_token, row)``. The raw token is returned exactly once, for
    the caller to write into the response cookie — it is never stored and never
    logged (backend/CLAUDE.md); log ``row.id`` instead.

    Flushes so the row's server-generated ``id`` is populated, but does not
    commit — the caller owns the transaction boundary.
    """
    now = now or datetime.now(timezone.utc)
    raw_token = generate_refresh_token()
    token = RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=now + REFRESH_TOKEN_TTL,
    )
    db.add(token)
    db.flush()
    return raw_token, token


def find_refresh_token(db: Session, raw_token: str) -> RefreshToken | None:
    """Look up the row for a raw refresh token, in *any* state.

    Deliberately returns revoked and expired rows too: AUTH-11 has to tell
    "this token was rotated out" apart from "this token never existed" in
    order to trigger token-family revocation on replay, and a filter here would
    collapse those two cases into one. Pair with ``is_refresh_token_active``.
    """
    return db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(raw_token)
        )
    ).scalar_one_or_none()


def is_refresh_token_active(
    token: RefreshToken, *, now: datetime | None = None
) -> bool:
    """Whether a refresh-token row is still usable — unrevoked and unexpired."""
    now = now or datetime.now(timezone.utc)
    return token.revoked_at is None and token.expires_at > now
