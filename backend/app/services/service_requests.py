"""Filing a service request, as one operation with two callers.

``POST /service-requests`` (SR-6 .. SR-10, SR-14) was the only caller while it
was the only way to file one. The chat assistant's ``create_service_request``
tool is the second (specs/chatbot/design.md §4), and a tool that rebuilt the
insert itself would be a second implementation of SR-14's two-writes-or-neither
rule — free to drift, and drifting silently, since the endpoint's tests would
stay green while the assistant filed requests with no opening history row.

So the operation moved here and the route calls it. What did *not* move is
anything about HTTP: no status code, no response model, no query-parameter
validation. This module takes an already-validated
``ServiceRequestCreate`` and a ``User``, and returns the ORM row.
"""

from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from app.api.schemas.service_request import ServiceRequestCreate
from app.db.models import ServiceRequest, Status, StatusHistory, User

# The status every request starts in. Resolved against the `statuses` table on
# insert (api-phase design.md §4) — the column carries no server default on
# purpose, so this is the only thing that decides it.
OPEN_STATUS_NAME = "open"

# api-phase design.md §4 / §7: the server always sets this, and `'general'` is
# the only value in this phase. Set explicitly rather than left to the column's
# server default so SR-6's guarantee is visible in the code that makes it, not
# two files away.
DEFAULT_REQUEST_TYPE = "general"

# The three rows every `ServiceRequestOut` embeds, as loader options. Shared by
# the list route, the detail route and the re-read below, so one change covers
# every path that serialises a request. `load_visible_service_request` takes
# the same options and the sub-resource routes pass none — they use it as a
# pure visibility gate and should not pay for the joins.
DETAIL_OPTIONS = (
    joinedload(ServiceRequest.current_status),
    joinedload(ServiceRequest.requestor),
    joinedload(ServiceRequest.assignee),
)


def with_relations(stmt: Select) -> Select:
    """Eager-load the three rows every ``ServiceRequestOut`` embeds.

    Without this, serialising a page of *n* requests costs 1 + 3n queries: the
    page, then a status, a requestor and an assignee per row, each fetched
    lazily the moment Pydantic reads the attribute. All three relationships are
    many-to-one, so ``joinedload`` adds no rows to the result set and is safe
    alongside ``LIMIT`` — the caveat about ``joinedload`` and ``LIMIT`` applies
    to collections, which these are not.
    """
    return stmt.options(*DETAIL_OPTIONS)


def create_service_request(
    db: Session, *, requestor: User, payload: ServiceRequestCreate
) -> ServiceRequest:
    """File a request for ``requestor`` and return it, eager-loaded (SR-14).

    Three of the row's columns are never read from the payload (SR-10 / XC-8):
    ``requestor_id`` is the caller, ``request_type`` is ``'general'``, and
    ``current_status_id`` is whatever ``'open'``'s id is. ``ServiceRequestCreate``
    has no fields for them and ignores unknown keys, which is what makes the
    same guarantee hold for the chat tool: an ``input`` object in which the
    model invented a ``user_id`` or an ``assignee`` produces exactly the row a
    clean one would (CHAT-7).

    ``requestor`` is a ``User`` rather than a bare id on purpose — an id
    argument is the thing a caller can pass the *wrong* value for, and the chat
    path is precisely where a model-supplied identifier would otherwise be one
    plausible-looking line away from being used.
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
        requestor_id=requestor.id,
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
    # `GET .../status-changes` (api-phase design.md §5) shows a brand-new
    # request with no step reached at all — and SC-3 forbids the frontend from
    # inventing the missing row. Added to the same transaction as the insert
    # above: neither write may land without the other, so there is no state
    # where a request exists whose history denies it was ever opened.
    db.add(
        StatusHistory(
            service_request_id=new_id,
            status_id=open_status.id,
            changed_by_id=requestor.id,
        )
    )
    db.commit()

    # Re-read through the same eager-loading path the detail route uses, so a
    # 201 body is byte-identical to what a follow-up GET returns. The row's
    # server-side `created_at` / `updated_at` are only knowable after the
    # commit anyway, and lazily loading the three embedded objects here would
    # be the N+1 this module avoids everywhere else.
    return db.execute(
        with_relations(select(ServiceRequest)).where(ServiceRequest.id == new_id)
    ).scalar_one()
