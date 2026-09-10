"""Shared route dependencies (T-AUTH-2; requirements XC-5, XC-6).

Every protected route in every slice imports ``get_current_user`` or
``require_role`` from here and never re-reads a cookie or compares a role
itself (backend/CLAUDE.md). A route needing "any signed-in user" depends on
``get_current_user``; a route needing a specific role depends on
``require_role("admin")``, which composes on top of it rather than repeating
the token work.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.api.errors import ForbiddenError, UnauthenticatedError
from app.core.security import (
    ACCESS_COOKIE_NAME,
    InvalidAccessTokenError,
    decode_access_token,
)
from app.database import get_db
from app.db.models import User

# Ranked, not a flat set, because XC-6 is worded as a *minimum* role: an admin
# satisfies a route that asks for `user`. A flat equality check would read
# identically today (the only gated routes are admin-only) and then quietly
# lock admins out of the first `require_role("user")` route anyone writes.
ROLE_RANK: dict[str, int] = {"user": 0, "admin": 1}


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> User:
    """Resolve the caller from the access-token cookie, or 401 (XC-5).

    Every rejection path — no cookie, malformed token, bad signature, expired,
    unknown user, deactivated user — raises the same
    ``401``/``UNAUTHENTICATED`` envelope with the same message. The caller
    learns that their session is unusable, not which of those it was.

    The user row is loaded rather than trusting the token's claims alone.
    design.md §1 embeds `role` in the JWT precisely so this *could* be
    stateless, and that tradeoff is real — but the round-trip buys three
    things a claims-only check can't have:

    * ``GET /auth/me`` (AUTH-14) needs `first_name`/`last_name`, which are not
      in the claims.
    * A deactivated user would otherwise keep a working session for up to the
      full hour of their access token's life. AUTH-8 refuses inactive users at
      login; letting an already-issued token outlive the deactivation would
      make that a soft check.
    * A token for a since-deleted user would otherwise reach a route and fail
      as a foreign-key ``IntegrityError`` — a 500 where the honest answer is
      401.

    Because the row is loaded anyway, `role` is read from it rather than from
    the claim: same value in every normal case, but fresh rather than up to an
    hour stale if a role is changed out-of-band (which is how promotion works —
    there is no admin-promotion endpoint).
    """
    token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not token:
        raise UnauthenticatedError()

    try:
        claims = decode_access_token(token)
    except InvalidAccessTokenError:
        # Deliberately not chained into the response: `str(exc)` is PyJWT's
        # own wording ("Signature has expired") and would tell a caller which
        # check failed.
        raise UnauthenticatedError() from None

    user = db.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise UnauthenticatedError()
    return user


def require_role(role: str) -> Callable[..., User]:
    """Build a dependency that admits only callers at or above ``role`` (XC-6).

    Composes on ``get_current_user``, so an unauthenticated caller still gets
    ``401`` rather than ``403`` — "you may not" is only an honest answer once
    we know who is asking.
    """
    try:
        minimum = ROLE_RANK[role]
    except KeyError:
        # At import time, not request time: a typo in a route's decorator
        # should break the app on startup, not silently 403 in production.
        raise ValueError(
            f"Unknown role {role!r}; expected one of {sorted(ROLE_RANK)}"
        ) from None

    def _require_role(user: User = Depends(get_current_user)) -> User:
        # An unrecognised stored role ranks below everything and is denied.
        # The DB's CHECK constraint makes that unreachable today; if it ever
        # becomes reachable, denying is the right default.
        if ROLE_RANK.get(user.role, -1) < minimum:
            raise ForbiddenError()
        return user

    return _require_role
