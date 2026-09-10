"""The five auth endpoints (T-AUTH-3; design.md §2, AUTH-1 through AUTH-16).

Everything cryptographic is imported from ``app/core/security.py`` and
everything cross-cutting from ``app/api/`` — no ``jwt.encode``, no
``set_cookie``, no hand-built error body appears below (backend/CLAUDE.md).
What is left here is the part that is genuinely about auth as a *flow*: which
failures are indistinguishable from which, when a session begins, and when a
refresh token stops being trusted.

Transaction boundaries are explicit. ``get_db`` yields a session and closes it
without committing, so each handler that writes commits for itself, and the
one place a write must survive a rejected request — AUTH-11's family
revocation — commits before raising.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.errors import ConflictError, UnauthenticatedError
from app.api.schemas.auth import (
    LoginRequest,
    RegisteredUser,
    RegisterRequest,
    SessionUser,
)
from app.core.security import (
    REFRESH_COOKIE_NAME,
    clear_auth_cookies,
    create_access_token,
    find_refresh_token,
    hash_password,
    is_refresh_token_active,
    issue_refresh_token,
    set_access_cookie,
    set_refresh_cookie,
    verify_password,
)
from app.database import get_db
from app.db.models import RefreshToken, User

# The `/api/v1` half of the path is applied at mount time in `create_app()`.
router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_TAKEN_MESSAGE = "That email address is already registered."

# AUTH-7's exact wording. One message for "no such email", "wrong password"
# and "deactivated account" alike — see `login`.
LOGIN_FAILED_MESSAGE = "Incorrect email or password."


# --- helpers -----------------------------------------------------------------


def normalize_email(email: str) -> str:
    """Fold an address to the single form used for both storage and lookup.

    Postgres' unique index on ``users.email`` compares exactly, so without this
    ``Ada@example.com`` and ``ada@example.com`` would be two accounts, and a
    user who capitalised their address on the login form would be told their
    password was wrong. design.md §2 requires the address to be unique without
    saying how case is treated; folding makes the existing index enforce the
    reading a user would expect. Because every read and every write goes
    through this one function, storage and lookup cannot disagree — and the
    index still does the real enforcing, so a race can't slip a second casing
    past it.
    """
    return email.strip().lower()


def _email_taken(db: Session, email: str) -> bool:
    return db.execute(select(User.id).where(User.email == email)).first() is not None


@lru_cache(maxsize=1)
def _decoy_password_hash() -> str:
    """A real bcrypt hash of a value nobody knows, for logins that match no user.

    AUTH-7 rules out a *timing* difference as well as a content one. Returning
    early when the email matches nothing would skip bcrypt entirely, and the
    ~100ms gap between "took a while" and "came back instantly" is a usable
    oracle for whether an address is registered — the exact leak the shared
    error message exists to prevent.

    Computed on first use rather than at import so that the cost lands on a
    request rather than on every process start (including every test run that
    never logs in). The hashed value is random, so nothing can match it.
    """
    return hash_password(secrets.token_urlsafe(32))


def _start_session(db: Session, user: User, response: Response) -> None:
    """Issue an access cookie and a fresh refresh token for ``user`` (AUTH-6).

    Adds the refresh-token row to the session but does not commit — the caller
    owns the transaction, so that on the refresh path the old token's
    revocation and the new token's insert land together or not at all.
    """
    set_access_cookie(response, create_access_token(user_id=user.id, role=user.role))
    raw_refresh, _row = issue_refresh_token(db, user.id)
    # The raw token exists only here and in the cookie; the row stores its
    # hash (backend/CLAUDE.md — never log or persist it raw).
    set_refresh_cookie(response, raw_refresh)


def _revoke_all_active_tokens(db: Session, user_id: uuid.UUID) -> None:
    """Mark every live refresh token for ``user_id`` revoked (AUTH-11)."""
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )


# --- endpoints ---------------------------------------------------------------


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=RegisteredUser,
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> User:
    """Create an account (AUTH-1 through AUTH-5, AUTH-16).

    Does **not** sign the new user in: no cookie is set, and the caller is
    expected to send them to the login form (design.md §2). Registration and
    authentication stay separate events, which keeps this endpoint from being
    a way to mint a session.
    """
    email = normalize_email(payload.email)
    if _email_taken(db, email):
        raise ConflictError(EMAIL_TAKEN_MESSAGE)

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        # `role` and `is_active` are left unset so the column server defaults
        # ('user', true) decide them. AUTH-4/XC-8: the schema already dropped
        # any `role` in the body, and there is no assignment here that could
        # reintroduce one.
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # The check above loses to a registration for the same address that
        # committed in between; the unique index is what actually decides.
        # Both paths answer identically, so the race is invisible to callers.
        db.rollback()
        raise ConflictError(EMAIL_TAKEN_MESSAGE) from None

    # Loads the server-generated id, role, is_active and created_at while the
    # session is certainly still open — response serialization runs after this
    # function returns, and a lazy load there would be a 500.
    db.refresh(user)
    return user


@router.post("/login", response_model=SessionUser)
def login(
    payload: LoginRequest, response: Response, db: Session = Depends(get_db)
) -> User:
    """Start a session (AUTH-6 through AUTH-8)."""
    user = db.execute(
        select(User).where(User.email == normalize_email(payload.email))
    ).scalar_one_or_none()

    # Hashed unconditionally — against the real hash if there is one, against a
    # decoy otherwise — so all three failures below cost the same time as well
    # as returning the same body.
    password_ok = verify_password(
        payload.password,
        user.password_hash if user is not None else _decoy_password_hash(),
    )

    if user is None or not password_ok or not user.is_active:
        # AUTH-7 and AUTH-8 collapse into one response: unknown address, wrong
        # password and deactivated account are indistinguishable. Anything
        # more specific would confirm to an unauthenticated caller that an
        # address is registered here.
        raise UnauthenticatedError(LOGIN_FAILED_MESSAGE)

    _start_session(db, user, response)
    db.commit()
    db.refresh(user)
    return user


@router.get("/me", response_model=SessionUser)
def me(user: User = Depends(get_current_user)) -> User:
    """Who is signed in (AUTH-14, AUTH-15).

    The frontend's session bootstrap: cookie-based sessions live on the server,
    so this is how a freshly loaded page discovers whether it has one.

    ``get_current_user`` reads the access-token cookie and nothing else, which
    is AUTH-15's requirement rather than an omission — a `/me` that quietly
    refreshed would make an expired session indistinguishable from a live one,
    and refreshing is `/auth/refresh`'s job.
    """
    return user


@router.post("/refresh", response_model=SessionUser)
def refresh(
    request: Request, response: Response, db: Session = Depends(get_db)
) -> User:
    """Rotate the refresh token and reissue both cookies (AUTH-9 through AUTH-11).

    Reads the refresh cookie directly rather than depending on
    ``get_current_user``: the access token is expected to be expired by the
    time anything calls this, which is the whole point of the endpoint.
    """
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_token:
        raise UnauthenticatedError()

    # Looks up rows in any state on purpose — a revoked row and no row at all
    # mean very different things here (see `find_refresh_token`).
    token = find_refresh_token(db, raw_token)
    if token is None:
        raise UnauthenticatedError()

    if token.revoked_at is not None:
        # AUTH-11 — a token that was already rotated out has come back. Either
        # it was copied before rotation and is being used now, or the real
        # holder's copy was stolen after they rotated; either way the family
        # can no longer be told apart from an attacker's, so every live
        # sibling goes with it. The legitimate user is signed out and has to
        # log in again, which is the intended cost.
        _revoke_all_active_tokens(db, token.user_id)
        # Committed before raising: the response is an error, but the
        # revocation is the substantive part of AUTH-11 and must survive it.
        db.commit()
        raise UnauthenticatedError()

    if not is_refresh_token_active(token):
        # Unrevoked but past `expires_at` (AUTH-10). Not a theft signal, just
        # an old session — no family revocation.
        raise UnauthenticatedError()

    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        # XC-13's rule applies here too: a deactivated user's refresh token
        # stops working immediately, rather than buying them another 30 days.
        raise UnauthenticatedError()

    token.revoked_at = datetime.now(timezone.utc)
    _start_session(db, user, response)
    # One commit for the revocation and the replacement together — a crash
    # between them would otherwise leave the caller holding a dead cookie.
    db.commit()
    db.refresh(user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, db: Session = Depends(get_db)) -> Response:
    """End the session (AUTH-12, AUTH-13). Always ``204``.

    Deliberately not gated on ``get_current_user``. AUTH-13 makes logout
    idempotent, and a ``401`` for a caller whose session had already expired
    would fail their "sign out" click at the one moment it is least useful to
    argue about — and would leave the stale cookies sitting in their browser.
    Clearing the cookies is unconditional for the same reason.

    Returns the ``Response`` object directly so the body is genuinely empty:
    a ``204`` carrying a serialized `null` would be malformed.
    """
    response = Response(status_code=status.HTTP_204_NO_CONTENT)

    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_token:
        token = find_refresh_token(db, raw_token)
        if token is not None and token.revoked_at is None:
            token.revoked_at = datetime.now(timezone.utc)
            db.commit()

    clear_auth_cookies(response)
    return response
