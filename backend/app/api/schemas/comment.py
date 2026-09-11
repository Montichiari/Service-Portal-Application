"""Comment schemas (T-CM-0; design.md §6, CM-5 through CM-8).

``UserSummary`` is imported rather than restated — design.md §1 has one
embedded-user shape, and a second copy here would be free to drift from the
one a service request's ``requestor`` and a status change's ``changed_by``
serialise through.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.common import UTCDateTime
from app.api.schemas.user import UserSummary

# CM-6. The column is unbounded TEXT, so 5000 is design.md §6's deliberate
# validation ceiling rather than a storage limit — without it an over-long body
# would be stored rather than rejected, which is not what the contract says
# happens.
BodyField = Annotated[str, Field(min_length=1, max_length=5000)]


class CommentCreate(BaseModel):
    """``POST /service-requests/{id}/comments`` body (CM-5 through CM-8)."""

    # XC-8: `author_id` is absent as a field and an unknown key is *dropped*
    # rather than rejected, matching `ServiceRequestCreate`. XC-8's requirement
    # is that a field documented as "not accepted" must not change the outcome;
    # `extra="forbid"` would change it from "created, server value used" to a
    # 422, which is a different contract.
    model_config = ConfigDict(extra="ignore")

    body: BodyField
    # Defaulted rather than required (CM-8), and deliberately **not** rejected
    # here for a `user`-role caller: CM-7's answer is a 403, which the schema
    # layer cannot produce because it does not know who is asking. The route
    # decides, and the distinction matters — a 422 would report this as a
    # malformed body rather than as a permission the caller does not have.
    is_internal: bool = False


class CommentOut(BaseModel):
    """One comment, as design.md §6 writes it.

    ``is_internal`` is on every comment, including the ones a `user`-role
    caller receives — where it is always ``false``, because CM-2 filters the
    others out in the query. Emitting it unconditionally is what lets an admin
    UI mark a comment internal (CM-3) without a second response shape.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    author: UserSummary
    body: str
    is_internal: bool
    created_at: UTCDateTime
    updated_at: UTCDateTime
