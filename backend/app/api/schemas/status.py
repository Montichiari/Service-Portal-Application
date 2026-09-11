"""Status schemas (T-SR-0; design.md §1 "Standard object shapes", §3).

``StatusOut`` is the shape design.md §1 names ``Status`` and embeds wherever a
status appears — on a service request, and later on a ``StatusChange``. It
lives here rather than inside ``service_request.py`` so those later modules can
import it without importing the whole service-request contract to reach one
nested object.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class StatusOut(BaseModel):
    """One row of the ``statuses`` reference table (design.md §1)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    sort_order: int
    is_terminal: bool


class StatusList(BaseModel):
    """``GET /statuses``' body (ST-2).

    A bare ``{"items": [...]}``, deliberately **not** XC-10's paginated
    envelope: the table holds exactly four seeded rows, always, so ``total`` /
    ``page`` / ``page_size`` would be constants dressed up as data. A separate
    model rather than a raw dict so the shape reaches the OpenAPI document.
    """

    items: list[StatusOut]
