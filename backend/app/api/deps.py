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
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.errors import ForbiddenError, UnauthenticatedError
from app.api.schemas.common import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.core.security import (
    ACCESS_COOKIE_NAME,
    InvalidAccessTokenError,
    decode_access_token,
)
from app.database import get_db
from app.db.models import User

ADMIN_ROLE = "admin"

# Ranked, not a flat set, because XC-6 is worded as a *minimum* role: an admin
# satisfies a route that asks for `user`. A flat equality check would read
# identically today (the only gated routes are admin-only) and then quietly
# lock admins out of the first `require_role("user")` route anyone writes.
ROLE_RANK: dict[str, int] = {"user": 0, ADMIN_ROLE: 1}


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


def is_admin(user: User) -> bool:
    """Whether ``user`` sees everything, for the routes that scope by owner.

    Distinct from ``require_role("admin")``, which *gates* a route: SR-2, CM-3
    and the rest don't refuse a regular user, they show them less. Expressed
    against ``ROLE_RANK`` rather than ``user.role == "admin"`` so the role
    hierarchy has exactly one definition — a third role added above admin would
    otherwise gate correctly and scope wrongly.
    """
    return ROLE_RANK.get(user.role, -1) >= ROLE_RANK[ADMIN_ROLE]


# --- Pagination (XC-10, XC-11) -----------------------------------------------


@dataclass(frozen=True)
class Pagination:
    """A resolved, already-clamped ``?page`` / ``?page_size`` pair."""

    page: int
    page_size: int

    @property
    def offset(self) -> int:
        """Rows to skip. ``page`` is 1-based (XC-10), the offset is not."""
        return (self.page - 1) * self.page_size


def pagination_params(
    page: Annotated[int, Query(ge=1)] = DEFAULT_PAGE,
    page_size: Annotated[int, Query(ge=1)] = DEFAULT_PAGE_SIZE,
) -> Pagination:
    """XC-10's paging params for any list endpoint, with XC-11's clamp applied.

    The ceiling is **not** expressed as ``Query(le=MAX_PAGE_SIZE)``, which
    would read as the obvious way to write it and would do the opposite of what
    XC-11 asks: ``le`` rejects an over-large ``page_size`` with a 422, where
    XC-11 requires the request to succeed with the value clamped. The floor
    *is* a validation rule — ``page=0`` and ``page_size=0`` are nonsense a
    clamp would have to invent an answer for, so 422 is the honest response
    there.

    One dependency rather than per-route parameters so the clamp cannot be
    applied on three list endpoints and forgotten on the fourth.
    """
    return Pagination(page=page, page_size=min(page_size, MAX_PAGE_SIZE))
