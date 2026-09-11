"""Status-change endpoints (T-SC-0; design.md §5, SC-1 through SC-8).

The second sub-resource of a service request, so it answers the same parent
question comments do — *may the caller see the parent at all?* — through the
same ``get_visible_parent_request`` (SC-2, SC-8). A 404 from here is
byte-identical to SR-12's because it comes from the same place.

Two things are specific to this resource:

* **The write is a transition, not a row.** SC-5 has the history insert and the
  parent's ``current_status_id`` update land together or not at all. They are
  one ``commit()`` on one session for that reason — a request whose history
  disagrees with its current status is a state the system should have no way to
  reach (the same reasoning SR-14 records for creation).
* **Reading and writing have different audiences.** SC-1 lets anyone who can see
  the request read its history; SC-4 lets only an admin add to it. So the gate
  is on the ``POST`` alone and the ``GET`` inherits the parent's rule.

**Dependency order on the ``POST`` is a decision, not an accident.** SC-4 says
a `user`-role caller is refused 403; SC-8 says a caller without visibility into
the parent gets 404. A non-admin who cannot see the request is covered by both,
and only one answer can be sent. ``get_visible_parent_request`` is declared
first, so that case answers 404 — SC-8 names it specifically, it keeps this
route's three "no such request" answers byte-identical to the ``GET``'s and to
SR-12's, and 403-for-an-invisible-row is exactly the existence disclosure XC-7
exists to prevent. SC-4's own case — a `user` posting to a request they *can*
see — still answers 403, which is what that requirement is about.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import ADMIN_ROLE, Pagination, pagination_params, require_role
from app.api.errors import ValidationFailedError
from app.api.schemas.common import Page
from app.api.schemas.status_change import StatusChangeCreate, StatusChangeOut
from app.api.visibility import get_visible_parent_request
from app.database import get_db
from app.db.models import ServiceRequest, Status, StatusHistory, User

# The `/api/v1` half of the path is applied at mount time in `create_app()`.
# `{request_id}` is the name `get_visible_parent_request` reads, so the prefix
# and the dependency have to agree on it.
router = APIRouter(
    prefix="/service-requests/{request_id}/status-changes", tags=["status-changes"]
)

# The two rows every `StatusChangeOut` embeds, as loader options. Both are
# many-to-one, so `joinedload` cannot multiply the result set and is safe
# alongside `LIMIT`; lazily loading them costs 1 + 2n statements for a page of
# n, which no correctness assertion would ever notice.
_DETAIL_OPTIONS = (
    joinedload(StatusHistory.status),
    joinedload(StatusHistory.changed_by),
)


def _resolve_status(db: Session, status_id: uuid.UUID) -> Status:
    """Turn a body's ``status_id`` into a row, or raise SC-6's 422.

    Checked here rather than in the schema for the same reason SR-3's `?status=`
    filter is: the valid set is the ``statuses`` table, which a migration owns.
    A Literal or an Enum in the schema layer would be a second source of truth
    that a later seeded status could contradict — silently, since the schema
    would keep rejecting a value the database had started accepting.

    Raised *before* anything is added to the session, so SC-6's "SHALL NOT
    partially apply" holds without depending on a rollback to undo a write that
    was never made.
    """
    row = db.execute(select(Status).where(Status.id == status_id)).scalar_one_or_none()
    if row is None:
        raise ValidationFailedError(
            fields={"status_id": ["No status exists with that id."]}
        )
    return row


@router.get("", response_model=Page[StatusChangeOut])
def list_status_changes(
    pagination: Pagination = Depends(pagination_params),
    parent: ServiceRequest = Depends(get_visible_parent_request),
    db: Session = Depends(get_db),
) -> Page[StatusChangeOut]:
    """This request's transitions, oldest first (SC-1 to SC-3, XC-10, XC-11).

    No role branch: SC-1 gives the history to whoever can see the request, and
    the parent dependency has already decided that. Unlike comments, there is no
    per-row audience — a transition is a fact about the request, not a note
    about it.

    Every row returned is a row that exists (SC-3). That is not enforced by
    anything here so much as by there being nothing here that could invent one:
    the un-reached statuses a stepper draws hollow are absent from this query's
    table, and design.md §5 puts that merge in the frontend deliberately.
    """
    conditions = [StatusHistory.service_request_id == parent.id]

    total = db.execute(
        select(func.count()).select_from(StatusHistory).where(*conditions)
    ).scalar_one()

    rows = (
        db.execute(
            select(StatusHistory)
            .options(*_DETAIL_OPTIONS)
            .where(*conditions)
            # SC-1's order — the opposite of SR-15's newest-first list, because
            # this reads as a timeline rather than as an inbox. `id` breaks
            # ties: Postgres' `now()` is transaction-scoped, so two transitions
            # written by one transaction share a `changed_at` exactly, and
            # equal-keyed rows come back in whatever order the planner likes —
            # which under paging means a row can appear on two pages or none.
            .order_by(StatusHistory.changed_at.asc(), StatusHistory.id.asc())
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )
        .scalars()
        .all()
    )

    return Page[StatusChangeOut](
        items=[StatusChangeOut.model_validate(row) for row in rows],
        total=total,
        page=pagination.page,
        # The clamped value, not what was asked for (XC-11).
        page_size=pagination.page_size,
    )


@router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=StatusChangeOut
)
def create_status_change(
    payload: StatusChangeCreate,
    # Declared before the role gate on purpose — see the module docstring. It is
    # also a `Depends()` rather than the handler's first statement, which is the
    # requirement and not a style choice: SC-8 asks for the 404 *before*
    # `status_id` is evaluated, and FastAPI validates a declared body only after
    # every dependency has resolved. Written inside the handler, the check would
    # run after Pydantic had already answered 422 — telling a caller who cannot
    # see the request that their body was the wrong shape, which confirms the
    # request exists.
    parent: ServiceRequest = Depends(get_visible_parent_request),
    admin: User = Depends(require_role(ADMIN_ROLE)),
    db: Session = Depends(get_db),
) -> StatusChangeOut:
    """Transition a request, as an admin (SC-4 to SC-7).

    ``changed_by_id`` is the authenticated admin and is never read from the body
    (XC-8) — the schema has no field for it, so a body supplying one produces
    exactly the same row as one that doesn't.
    """
    new_status = _resolve_status(db, payload.status_id)

    change = StatusHistory(
        service_request_id=parent.id,
        status_id=new_status.id,
        changed_by_id=admin.id,
        # SC-7: stored verbatim, `None` when omitted.
        note=payload.note,
    )
    db.add(change)
    # SC-5's second write. `parent` is a live row on this same session, so the
    # assignment is part of the same unit of work as the insert above — one
    # `commit()` below covers both, and neither can land without the other.
    # Issuing this as its own transaction (or committing between the two) is the
    # failure this requirement exists to forbid: a request whose history says
    # `in_progress` while its `current_status_id` still says `open`.
    parent.current_status_id = new_status.id
    # Flushed before the commit so the server-generated id is readable without
    # depending on what the session expires on commit.
    db.flush()
    new_id = change.id
    db.commit()

    # Re-read through the same eager-loading path the list route uses, so the
    # 201 body is assembled identically to the one a follow-up GET returns — and
    # so `status` and `changed_by` are a join rather than lazy loads after the
    # commit expired them. `changed_at` is server-generated and only knowable
    # after the write anyway.
    created = db.execute(
        select(StatusHistory)
        .options(*_DETAIL_OPTIONS)
        .where(StatusHistory.id == new_id)
    ).scalar_one()
    return StatusChangeOut.model_validate(created)
