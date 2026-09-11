"""Who may see a service request — one predicate, for every route that asks.

SR-1 / SR-2 decide which requests a caller can reach, and SR-11 through SR-13
decide what happens when they reach for one they cannot. Comments (CM-4, CM-9)
and status changes (SC-2, SC-8) all defer to *that* rule rather than restating
it: a comment is visible exactly when its parent request is. Extracted here
during ``T-CM-0`` from ``routes/service_requests.py``, where it lived while
only one router needed it — two copies of a visibility predicate is the shape
of bug where one of them is later tightened and the other is not.

The module is deliberately not ``deps.py``: that one holds the auth and
pagination dependencies every resource uses, and this is a service-request
rule that other resources borrow. It is not ``routes/service_requests.py``
either, because a router importing another router to reach a helper is how
route modules start depending on each other's ordering.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, is_admin
from app.api.errors import NotFoundError
from app.database import get_db
from app.db.models import ServiceRequest, User


def parse_uuid_or_none(raw: str) -> uuid.UUID | None:
    """Parse a path id, or ``None`` — never an exception the caller can see.

    SR-13 makes a malformed id a 404, identical to a missing row. Typing the
    path parameter as ``uuid.UUID`` would hand that case to FastAPI, which
    answers 422 before the handler runs — a different status *and* a body
    naming the failure, which is precisely the distinction XC-7 forbids. So
    the parameter arrives as ``str`` and this turns a parse failure into the
    same "no such row" a lookup miss produces.
    """
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


def service_request_conditions(user: User) -> list[Any]:
    """SR-1 / SR-2 as ``WHERE`` clauses: owners see their own, admins see all.

    Returned as conditions rather than applied to a statement so the *same*
    list goes into both an item query and its count. Two call sites, one
    predicate — a `total` that disagreed with the page would be a slow-burning
    bug, visible only as a paginator that promises rows it never delivers.
    """
    if is_admin(user):
        return []
    return [ServiceRequest.requestor_id == user.id]


def load_visible_service_request(
    db: Session,
    raw_id: str,
    user: User,
    *,
    options: Sequence[Any] = (),
) -> ServiceRequest:
    """Fetch one request the caller may see, or raise 404 (SR-11 to SR-13).

    All three of "not a valid id", "no such row" and "exists but is someone
    else's" leave through this one ``raise``, so they cannot answer differently
    — not in status, not in message, not in whether ``fields`` is present.
    Ownership is in the ``WHERE`` clause rather than compared after the fetch:
    same answer either way today, but a post-fetch check is one early return
    away from becoming a 403 that confirms the row exists.

    ``options`` lets a caller that will serialise the row eager-load what it
    embeds. A caller that only needs the row's *existence* — the comment and
    status-change routes, which want the parent as a gate and read nothing off
    it but ``id`` — passes nothing and pays for no joins.
    """
    request_id = parse_uuid_or_none(raw_id)
    if request_id is None:
        raise NotFoundError()

    stmt = (
        select(ServiceRequest)
        .options(*options)
        .where(ServiceRequest.id == request_id, *service_request_conditions(user))
    )
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        raise NotFoundError()
    return row


def get_visible_parent_request(
    request_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ServiceRequest:
    """The parent request of a sub-resource route, or 404 (CM-4, CM-9).

    A **dependency**, not a call at the top of each handler, and that is the
    requirement rather than a style choice: CM-9 asks for the 404 *before*
    ``body`` or ``is_internal`` is evaluated, and FastAPI resolves a route's
    dependencies before it validates the request body. A visibility check
    written as the handler's first statement would run after Pydantic had
    already rejected a malformed body with a 422 — telling a caller who cannot
    see the request that their comment was the wrong shape, which confirms the
    request exists.
    """
    return load_visible_service_request(db, request_id, user)
