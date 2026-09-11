"""Service request schemas (T-SR-0; design.md §4, SR-5 through SR-10).

``StatusOut`` and ``UserSummary`` are imported, never restated — they are
design.md §1's shared object shapes, and a second copy here would be free to
drift from the one the comment and status-change payloads embed.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.common import UTCDateTime
from app.api.schemas.status import StatusOut
from app.api.schemas.user import UserSummary

# SR-4 / SR-9's accepted set, matching the `ck_service_requests_priority_valid`
# CHECK constraint. Declared once and used for both the create body and the
# list filter, so a route can never accept a priority the column would reject.
Priority = Literal["low", "medium", "high"]

# design.md §4: 1-200 chars, matching `service_requests.title`'s VARCHAR(200).
# Without the ceiling an over-long title would pass validation and fail at the
# INSERT as a 500 where SR-7 wants a 422.
TitleField = Annotated[str, Field(min_length=1, max_length=200)]

# SR-8. The column is unbounded TEXT, so 10000 is a deliberate abuse backstop
# rather than a storage limit (design.md §4) — and it is not the frontend's
# 1000-character UX cap, which stays where it is.
DescriptionField = Annotated[str, Field(min_length=1, max_length=10000)]


class ServiceRequestCreate(BaseModel):
    """``POST /service-requests`` body (SR-6 through SR-10)."""

    # XC-8/SR-10: `requestor_id`, `request_type` and `current_status_id` are
    # absent as fields, and an unknown key is *dropped* rather than rejected.
    # That distinction is the requirement, not a detail — XC-8 says a field
    # documented as "not accepted" must not change the outcome, and
    # `extra="forbid"` would change it from "created, server value used" to a
    # 422. Pydantic already defaults to "ignore"; spelling it out is what stops
    # a later `extra="forbid"` from looking like a tightening rather than a
    # contract break.
    model_config = ConfigDict(extra="ignore")

    title: TitleField
    description: DescriptionField
    # Required, and a Literal — so SR-9's 422 comes from the validation layer
    # with `fields.priority` populated, rather than from a hand-written check.
    priority: Priority


class ServiceRequestOut(BaseModel):
    """The one ``ServiceRequest`` shape, for list and detail alike.

    design.md §0 decision 2: not two shapes. ``description`` is present in both
    (SR-5) — one text field per row is cheap next to having two payloads that
    are almost the same, which is the inconsistency this contract exists to
    resolve.

    Fields are ordered as design.md §4 writes them.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    request_type: str
    priority: str
    # The ORM attribute is `current_status` (the column is `current_status_id`);
    # the contract calls it `status`. The aliases bridge those without either
    # side renaming to suit the other: `validation_alias` is the attribute read
    # off the row, the field name is what appears in JSON. Both are spelled out
    # because FastAPI serialises response models with `by_alias=True`, so
    # relying on the field name alone would depend on there being no
    # serialization alias — true today, and quietly untrue the moment someone
    # adds one.
    status: StatusOut = Field(
        validation_alias="current_status", serialization_alias="status"
    )
    requestor: UserSummary
    # Always null in this phase — there is no assignment path yet (design.md
    # §7 defers `PATCH /service-requests/{id}`). Typed optional because the
    # column is nullable, not because it is sometimes populated.
    assignee: UserSummary | None
    created_at: UTCDateTime
    updated_at: UTCDateTime
    description: str
