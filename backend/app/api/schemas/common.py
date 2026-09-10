"""Field types shared by more than one resource's schemas.

Not a resource module — the "one file per resource" rule (backend/CLAUDE.md)
is about the resource schemas themselves. This is where a type that several of
them need lives, so the rule it enforces is written down once.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic import PlainSerializer


def _as_utc_iso8601(value: datetime) -> str:
    """Render a timestamp the way XC-2 requires: ISO 8601, UTC, explicit offset.

    Pydantic's own datetime serializer emits whatever offset the value carries,
    so a database session running in a non-UTC timezone would produce
    ``2026-09-04T11:12:00+02:00`` — still valid ISO 8601, but not what XC-2
    specifies and not what a frontend comparing strings would expect. Shifting
    to UTC here makes the response independent of the server's timezone.
    """
    if value.tzinfo is None:
        # Every timestamp column in this schema is TIMESTAMPTZ (design.md R1),
        # so psycopg2 hands back aware datetimes and this branch should be
        # unreachable. Treating a naive value as UTC beats emitting an offsetless
        # string that a client would silently read as local time.
        value = value.replace(tzinfo=timezone.utc)
    # `isoformat()` writes UTC as "+00:00"; XC-2's example uses the equivalent
    # "Z", which is what every other JSON API the frontend will meet emits.
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


UTCDateTime = Annotated[datetime, PlainSerializer(_as_utc_iso8601, return_type=str)]
"""A ``datetime`` response field rendered per XC-2."""
