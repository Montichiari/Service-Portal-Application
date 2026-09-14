"""Service request endpoints (T-SR-0; design.md §4, SR-1 through SR-15).

Three routes, and one idea running through all of them: **who may see a row is
part of the query, never part of what happens to the rows afterwards.** A
regular user's scope is a ``WHERE`` clause on the list query, on the count that
accompanies it, and on the single-row fetch. Filtering in Python after the
fact would return short pages and a ``total`` counting rows the caller cannot
see — and would leak existence through the difference between 404 and 403.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import Pagination, get_current_user, pagination_params
from app.api.errors import ValidationFailedError
from app.api.schemas.common import Page
from app.api.schemas.service_request import (
    Priority,
    ServiceRequestCreate,
    ServiceRequestOut,
)
from app.api.visibility import (
    load_visible_service_request,
    service_request_conditions,
)
from app.database import get_db
from app.db.models import ServiceRequest, Status, User
from app.services.service_requests import (
    DETAIL_OPTIONS,
    create_service_request as create_service_request_record,
    with_relations,
)

# The `/api/v1` half of the path is applied at mount time in `create_app()`.
router = APIRouter(prefix="/service-requests", tags=["service-requests"])

# `OPEN_STATUS_NAME`, `DEFAULT_REQUEST_TYPE`, `DETAIL_OPTIONS` and
# `with_relations` moved to `app/services/service_requests.py` when the chat
# assistant's `create_service_request` tool became a second caller of the
# insert (specs/chatbot/design.md §4). They are imported above rather than
# re-declared: the loader options in particular have to be the *same* tuple the
# service's post-insert re-read uses, or a 201 body could embed a lazily
# loaded object where a GET embeds a joined one.


# --- helpers -----------------------------------------------------------------


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


# --- endpoints ---------------------------------------------------------------


@router.get(
    "",
    response_model=Page[ServiceRequestOut],
    summary="List service requests visible to the caller",
)
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
    conditions = service_request_conditions(user)

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
            with_relations(select(ServiceRequest))
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
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ServiceRequestOut,
    summary="File a service request",
)
def create_service_request(
    payload: ServiceRequestCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ServiceRequestOut:
    """File a request on behalf of the caller (SR-6 to SR-10, SR-14).

    The insert itself lives in ``app/services/service_requests.py``, because the
    chat assistant's ``create_service_request`` tool files requests through the
    same operation (specs/chatbot/design.md §4). What stays here is the part
    that is about HTTP: the validated body, the authenticated caller, the 201,
    and the response model.

    Three of the row's columns are never read from the body (SR-10 / XC-8) —
    see the service function, which is where that guarantee is now made.
    """
    return ServiceRequestOut.model_validate(
        create_service_request_record(db, requestor=user, payload=payload)
    )


@router.get(
    "/{request_id}",
    response_model=ServiceRequestOut,
    summary="Fetch one service request",
)
def get_service_request(
    request_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ServiceRequestOut:
    """One request, if the caller may see it (SR-11 to SR-13).

    ``request_id`` is typed ``str`` deliberately — see ``parse_uuid_or_none``.
    """
    return ServiceRequestOut.model_validate(
        load_visible_service_request(db, request_id, user, options=DETAIL_OPTIONS)
    )
