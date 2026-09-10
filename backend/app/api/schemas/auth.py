"""Auth request/response schemas (T-AUTH-3; design.md §2).

These are the contract, not a convenience layer: the response models here are
what keeps ``password_hash`` out of every body AUTH-5 covers, and the request
models are what turns a bad field into XC-4's ``422`` envelope instead of a
crash further down.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.api.schemas.common import UTCDateTime
from app.core.security import MAX_PASSWORD_BYTES

# `users.email` is VARCHAR(255); without the ceiling a 400-character address
# would pass validation and fail at the INSERT as a 500 instead of a 422.
EmailField = Annotated[EmailStr, Field(max_length=255)]

# 1-100 chars, matching the `first_name` / `last_name` columns (design.md §2).
NameField = Annotated[str, Field(min_length=1, max_length=100)]

# AUTH-3. Length only — no composition rule. This is a decided policy, not an
# unfinished one: composition rules push people toward predictable
# substitutions (`P@ssw0rd1` satisfies most of them) while length is the factor
# that actually drives strength, per NIST SP 800-63B. Don't "complete" this
# with an uppercase/digit/symbol regex; that rule was considered and rejected.
MIN_PASSWORD_CHARS = 12


class RegisterRequest(BaseModel):
    """``POST /auth/register`` body (AUTH-1, AUTH-3, AUTH-4, AUTH-16)."""

    # AUTH-4 / XC-8: `role` is not a field here, and an unknown key is dropped
    # rather than rejected — so a body carrying `"role": "admin"` registers a
    # perfectly ordinary user. Pydantic's default is already "ignore"; it is
    # spelled out because a future `extra="allow"` would quietly turn that
    # ignored key into an accepted one.
    model_config = ConfigDict(extra="ignore")

    first_name: NameField
    last_name: NameField
    email: EmailField
    password: Annotated[str, Field(min_length=MIN_PASSWORD_CHARS)]

    @field_validator("password")
    @classmethod
    def _within_bcrypt_limit(cls, value: str) -> str:
        """AUTH-16 — reject over-long passwords here, as a 422.

        ``hash_password`` raises on anything past bcrypt's hard limit, which
        without this check would surface as a ``500``. The limit is imported,
        never re-typed as another literal ``72`` (backend/CLAUDE.md).

        Measured in **bytes**, which is why this is a validator rather than a
        ``max_length``: ``max_length`` counts characters, and a password of 30
        emoji is 30 characters and 120 bytes.
        """
        size = len(value.encode("utf-8"))
        if size > MAX_PASSWORD_BYTES:
            # The message says what the limit is and why the count may not
            # match what was typed. It never quotes the password back — the
            # error envelope carries `msg` into the response body.
            raise ValueError(
                f"Password must be at most {MAX_PASSWORD_BYTES} bytes; this "
                f"one is {size}. Accented and non-Latin characters, and emoji, "
                f"count as more than one byte each."
            )
        return value


class LoginRequest(BaseModel):
    """``POST /auth/login`` body (AUTH-6, AUTH-7)."""

    model_config = ConfigDict(extra="ignore")

    email: EmailField
    # Deliberately unconstrained, unlike the register schema's. A length rule
    # here would answer "that isn't long enough to be one of our passwords"
    # with a 422 where AUTH-7 wants an indistinguishable 401 — and it would
    # lock out any account whose password predates a future policy change.
    password: str


class SessionUser(BaseModel):
    """Who the caller is — login, refresh and ``/auth/me`` all return this.

    One shape for all three (design.md §2) so the frontend has a single
    "current user" type regardless of which call produced it. No `email`, no
    timestamps, and — the point of the model existing — no `password_hash`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    first_name: str
    last_name: str
    role: str


class RegisteredUser(BaseModel):
    """``POST /auth/register``'s ``201`` body (AUTH-1).

    Field-for-field from design.md §2, in that order. Not built by extending
    ``SessionUser``: the two overlap today by coincidence of what registration
    happens to echo back, and tying them together would propagate any later
    change to the session shape into the registration contract.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    first_name: str
    last_name: str
    # Plain `str`, not `EmailStr`: validating an address on the way *out* can
    # only fail on a row that is already stored, turning a readable 201 into a
    # 500. The inbound schema is where an address has to be well-formed.
    email: str
    role: str
    created_at: UTCDateTime
