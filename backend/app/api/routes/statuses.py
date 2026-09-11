"""The statuses reference endpoint (T-SR-0; design.md §3, ST-1, ST-2).

One route, and the only unauthenticated read in the API. That is deliberate
(ST-1): the four rows are static reference data with nothing user-specific in
them, and the status stepper that consumes them renders for every role. Gating
it would mean the frontend could not draw a status legend before knowing who
is looking.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas.status import StatusList, StatusOut
from app.database import get_db
from app.db.models import Status

# The `/api/v1` half of the path is applied at mount time in `create_app()`.
router = APIRouter(prefix="/statuses", tags=["statuses"])


@router.get("", response_model=StatusList)
def list_statuses(db: Session = Depends(get_db)) -> StatusList:
    """Every seeded status, in display order (ST-1, ST-2).

    Ordered by ``sort_order`` in SQL, not by insertion or by name: the column
    exists precisely so the stepper's order is data rather than a convention
    the frontend has to re-know. ``open`` before ``closed`` is not
    alphabetical, and rows come back in no guaranteed order without an
    ``ORDER BY``.
    """
    rows = (
        db.execute(select(Status).order_by(Status.sort_order.asc())).scalars().all()
    )
    return StatusList(items=[StatusOut.model_validate(row) for row in rows])
