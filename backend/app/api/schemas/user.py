"""User schemas shared across resources (T-SR-0; design.md §1).

``UserSummary`` is design.md §1's embedded user reference — the shape that
appears as a request's ``requestor`` / ``assignee``, and later as a comment's
``author`` and a status change's ``changed_by``. Because four resources embed
it, it lives in its own module rather than in whichever one happened to need it
first.

Deliberately not the full ``User`` resource: no ``email``, no timestamps, and —
the reason a response schema exists at all (AUTH-5, XC-15) — no
``password_hash``. It is a reference for display, not an identity endpoint.

Distinct from ``schemas/auth.py``'s ``SessionUser`` despite the fields
currently matching. That one answers "who is signed in" and is free to grow
session-specific fields; this one is how *other* people appear inside someone
else's payload. Fusing them would make any change to either contract silently
change the other.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class UserSummary(BaseModel):
    """A user reference embedded in another resource (design.md §1)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    first_name: str
    last_name: str
    # Plain `str`, not a Literal: this validates on the way *out*, so a value
    # the CHECK constraint somehow let through would turn a readable 200 into a
    # 500. Inbound schemas are where a role has to be one of the known two.
    role: str
