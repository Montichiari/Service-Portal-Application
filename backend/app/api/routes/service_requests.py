"""Service request endpoints (T-SR-0; design.md §4, SR-1 through SR-15).

Three routes, and one idea running through all of them: **who may see a row is
part of the query, never part of what happens to the rows afterwards.** A
regular user's scope is a ``WHERE`` clause on the list query, on the count that
accompanies it, and on the single-row fetch. Filtering in Python after the
fact would return short pages and a ``total`` counting rows the caller cannot
see — and would leak existence through the difference between 404 and 403.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import Pagination, get_current_user, is_admin, pagination_params
from app.api.errors import NotFoundError, ValidationFailedError
from app.api.schemas.common import Page
from app.api.schemas.service_request import (
    Priority,
    ServiceRequestCreate,
    ServiceRequestOut,
)
from app.database import get_db
from app.db.models import ServiceRequest, Status, StatusHistory, User

# The `/api/v1` half of the path is applied at mount time in `create_app()`.
router = APIRouter(prefix="/service-requests", tags=["service-requests"])

# The status every request starts in. Resolved against the `statuses` table on
# insert (design.md §4) — the column carries no server default on purpose, so
# this is the only thing that decides it.
OPEN_STATUS_NAME = "open"

# design.md §4 / §7: the server always sets this, and `'general'` is the only
# value in this phase. Set explicitly rather than left to the column's server
# default so SR-6's guarantee is visible in the code that makes it, not two
# files away.
DEFAULT_REQUEST_TYPE = "general"


# --- helpers -----------------------------------------------------------------


def _with_relations(stmt: Select) -> Select:
    """Eager-load the three rows every ``ServiceRequestOut`` embeds.

    Without this, serialising a page of *n* requests costs 1 + 3n queries: the
    page, then a status, a requestor and an assignee per row, each fetched
    lazily the moment Pydantic reads the attribute. All three relationships are
    many-to-one, so ``joinedload`` adds no rows to the result set and is safe
    alongside ``LIMIT`` — the caveat about ``joinedload`` and ``LIMIT`` applies
    to collections, which these are not.
    """
    return stmt.options(
        joinedload(ServiceRequest.current_status),
        joinedload(ServiceRequest.requestor),
        joinedload(ServiceRequest.assignee),
    )


def _visibility_conditions(user: User) -> list:
    """SR-1 / SR-2 as ``WHERE`` clauses: owners see their own, admins see all.

    Returned as conditions rather than applied to a statement so the *same*
    list goes into both the item query and the count. Two call sites, one
    predicate — a `total` that disagreed with the page would be a slow-burning
    bug, visible only as a paginator that promises rows it never delivers.
    """
    if is_admin(user):
        return []
    return [ServiceRequest.requestor_id == user.id]


def _resolve_status_filter(db: Session, name: str) -> Status:
    """Turn ``?status=<name>`` into a row, or raise SR-3's 422.

    The valid set is the ``statuses`` table, not a Literal in this file — the
    rows are seed data a migration owns, and duplicating their names here would
    create a second source of truth that a later status could contradict. That
    is why this check cannot live in the schema layer and produces its 422 by
    hand.

    An unknown name is a 422 rather than an empty 200 (SR-3) because the two
    answer different questions: "no requests match" and "there is no such
    status" look identical to a caller who gets an empty list, and only one of
    them means they should fix their request.
    """
    row = db.execute(select(Status).where(Status.name == name)).scalar_one_or_none()
    if row is None:
        known = (
            db.execute(select(Status.name).order_by(Status.sort_order.asc()))
            .scalars()
            .all()
        )
        raise ValidationFailedError(
            fields={"status": [f"Must be one of: {', '.join(known)}."]}
        )
    return row


def _parse_uuid(raw: str) -> uuid.UUID | None:
    """Parse a path id, or ``None`` — never an exception the caller can see.

    SR-13 makes a malformed id a 404, identical to a missing row. Typing the
    path parameter as ``uuid.UUID`` would hand that case to FastAPI, which
    answers 422 before the handler runs — a different status *and* a body
    naming the failure, which is precisely the distinction XC-7 forbids. So
    the parameter arrives as ``str`` and this turns a parse failure into the
    same "no such row" the lookup below produces.
    """
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


def _load_visible(db: Session, raw_id: str, user: User) -> ServiceRequest:
    """Fetch one request the caller may see, or raise 404 (SR-11 to SR-13).

    All three of "not a valid id", "no such row" and "exists but is someone
    else's" leave through this one ``raise``, so they cannot answer differently
    — not in status, not in message, not in whether ``fields`` is present.
    Ownership is in the ``WHERE`` clause rather than compared after the fetch:
    same answer either way today, but a post-fetch check is one early return
    away from becoming a 403 that confirms the row exists.
    """
    request_id = _parse_uuid(raw_id)
    if request_id is None:
        raise NotFoundError()

    stmt = _with_relations(select(ServiceRequest)).where(
        ServiceRequest.id == request_id, *_visibility_conditions(user)
    )
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        raise NotFoundError()
    return row


# --- endpoints ---------------------------------------------------------------


@router.get("", response_model=Page[ServiceRequestOut])
def list_service_requests(
    pagination: Pagination = Depends(pagination_params),
    # Named `status_name` in Python and `status` on the wire. The alias is what
    # a caller sends and what XC-4's `fields` key is built from, so SR-3's
    # error still lands on `fields.status`.
    status_name: str | None = Query(default=None, alias="status"),
    # A Literal, so SR-4's 422 comes from the validation layer with
    # `fields.priority` populated — the status filter cannot do the same
    # because its valid set lives in the database (see `_resolve_status_filter`).
    priority: Priority | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[ServiceRequestOut]:
    """A page of requests the caller may see (SR-1 to SR-5, SR-15, XC-10, XC-11)."""
    conditions = _visibility_conditions(user)

    if status_name is not None:
        # Filtering on `current_status_id` rather than joining `statuses` and
        # comparing names: resolving the name to a row is already required for
        # SR-3's 422, so the filter gets an indexed id comparison for free.
        conditions.append(
            ServiceRequest.current_status_id
            == _resolve_status_filter(db, status_name).id
        )

    if priority is not None:
        conditions.append(ServiceRequest.priority == priority)

    # Counted with the same predicate the page uses, so `total` is the number
    # of rows *this caller* can reach (XC-10).
    total = db.execute(
        select(func.count()).select_from(ServiceRequest).where(*conditions)
    ).scalar_one()

    rows = (
        db.execute(
            _with_relations(select(ServiceRequest))
            .where(*conditions)
            # SR-15: newest first, with `id` breaking ties. The tiebreaker is
            # not decoration — Postgres' `now()` is transaction-scoped, so
            # every row written by one request shares a `created_at` exactly,
            # and equal-keyed rows come back in whatever order the planner
            # likes. Without it a row can appear on both page 1 and page 2, or
            # on neither, and the bug only shows up under paging.
            .order_by(ServiceRequest.created_at.desc(), ServiceRequest.id.desc())
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )
        .scalars()
        .all()
    )

    return Page[ServiceRequestOut](
        items=[ServiceRequestOut.model_validate(row) for row in rows],
        total=total,
        page=pagination.page,
        # The clamped value, not what was asked for (XC-11) — a caller who
        # sent `page_size=250` needs to know they got 100, or their next
        # `page=2` skips 150 rows that were never shown.
        page_size=pagination.page_size,
    )


@router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=ServiceRequestOut
)
def create_service_request(
    payload: ServiceRequestCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ServiceRequestOut:
    """File a request on behalf of the caller (SR-6 to SR-10, SR-14).

    Three of the row's columns are never read from the body (SR-10 / XC-8):
    ``requestor_id`` is the authenticated user, ``request_type`` is
    ``'general'``, and ``current_status_id`` is whatever ``'open'``'s id is.
    The schema has no fields for them, so a body supplying all three is
    accepted and creates exactly the same row as one that doesn't — which is
    XC-8's actual requirement, and the reason the schema ignores unknown keys
    rather than rejecting them.
    """
    open_status = db.execute(
        select(Status).where(Status.name == OPEN_STATUS_NAME)
    ).scalar_one_or_none()
    if open_status is None:
        # An unseeded database, not a bad request. Raising here surfaces as
        # XC-14's 500 with the traceback logged server-side; the alternatives
        # are worse in both directions — a NULL `current_status_id` would fail
        # as a bare IntegrityError, and inventing a status row would paper over
        # a broken deployment.
        raise RuntimeError(
            f"No {OPEN_STATUS_NAME!r} row in `statuses`: the reference data "
            "migration has not been applied to this database."
        )

    request = ServiceRequest(
        requestor_id=user.id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        request_type=DEFAULT_REQUEST_TYPE,
        current_status_id=open_status.id,
    )
    db.add(request)
    # Flushed, not committed: this assigns the server-generated id that the
    # history row needs while both writes are still inside one transaction.
    db.flush()
    new_id = request.id

    # SR-14. A request's history has to start where the request starts, or the
    # stepper the frontend builds by merging `GET /statuses` against
    # `GET .../status-changes` (design.md §5) shows a brand-new request with no
    # step reached at all — and SC-3 forbids the frontend from inventing the
    # missing row. Added to the same transaction as the insert above: neither
    # write may land without the other, so there is no state where a request
    # exists whose history denies it was ever opened.
    db.add(
        StatusHistory(
            service_request_id=new_id,
            status_id=open_status.id,
            changed_by_id=user.id,
        )
    )
    db.commit()

    # Re-read through the same eager-loading path the detail route uses, so the
    # 201 body is byte-identical to what a follow-up GET returns. The row's
    # server-side `created_at` / `updated_at` are only knowable after the
    # commit anyway, and lazily loading the three embedded objects here would
    # be the N+1 this module avoids everywhere else.
    created = db.execute(
        _with_relations(select(ServiceRequest)).where(ServiceRequest.id == new_id)
    ).scalar_one()
    return ServiceRequestOut.model_validate(created)


@router.get("/{request_id}", response_model=ServiceRequestOut)
def get_service_request(
    request_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ServiceRequestOut:
    """One request, if the caller may see it (SR-11 to SR-13).

    ``request_id`` is typed ``str`` deliberately — see ``_parse_uuid``.
    """
    return ServiceRequestOut.model_validate(_load_visible(db, request_id, user))
