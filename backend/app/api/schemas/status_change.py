"""Status-change schemas (T-SC-0; design.md §5, SC-5 through SC-7).

``StatusOut`` and ``UserSummary`` are imported rather than restated — design.md
§1 has one embedded status shape and one embedded user shape, and a second copy
here would be free to drift from the ones a service request and a comment
serialise through.

The resource is called ``StatusChange`` in the contract and ``StatusHistory``
in the ORM (the table is ``status_history``). Neither name is renamed to suit
the other: the DB names an audit log, the API names the event a client posted.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from app.api.schemas.common import UTCDateTime
from app.api.schemas.status import StatusOut
from app.api.schemas.user import UserSummary


class StatusChangeCreate(BaseModel):
    """``POST /service-requests/{id}/status-changes`` body (SC-5 to SC-7)."""

    # XC-8, matching `ServiceRequestCreate` and `CommentCreate`:
    # `changed_by_id`, `service_request_id` and `changed_at` are absent as
    # fields and an unknown key is *dropped* rather than rejected. XC-8's
    # requirement is that a field documented as "not accepted" must not change
    # the outcome; `extra="forbid"` would change it from "created, server value
    # used" to a 422, which is a different contract.
    model_config = ConfigDict(extra="ignore")

    # Required, and typed `UUID` deliberately — unlike the *path* id, which is
    # a `str` so that a malformed one becomes SR-13's 404 rather than a 422
    # (see `parse_uuid_or_none`). Here 422 is the right answer: SC-6 asks for it
    # with `fields.status_id` populated, and a malformed body value is the
    # caller's mistake to be told about, not a resource whose existence is being
    # withheld. Existence in `statuses` is checked in the route — Pydantic can
    # only rule on the shape.
    status_id: uuid.UUID
    # SC-7: optional, no enforced maximum (the column is unbounded TEXT), stored
    # verbatim. Absent and explicit `null` both mean "no note", which is what
    # the nullable column already expresses.
    note: str | None = None


class StatusChangeOut(BaseModel):
    """One transition, as design.md §5 writes it.

    Every field is of a row that actually happened. SC-3 forbids synthesising a
    placeholder for a status not yet reached, so there is no "pending" variant
    of this shape and no nullable ``changed_at`` — the frontend's stepper gets
    its un-reached steps by diffing this list against ``GET /statuses``, not by
    receiving hollow rows from here.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: StatusOut
    # Nullable, mirroring the column's ON DELETE SET NULL (design.md §5): a
    # transition made by a since-deleted user keeps its record and loses its
    # actor. Optional because the column is, not because the route ever writes
    # one without a caller.
    changed_by: UserSummary | None
    note: str | None
    changed_at: UTCDateTime
