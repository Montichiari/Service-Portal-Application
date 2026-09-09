"""ORM model package.

Re-exports every model so a single import registers them all on
``Base.metadata``. Any code that needs "every model registered" — most
notably ``alembic/env.py`` for autogenerate — imports from here, never from
the individual modules. Adding a model means adding its line here as part of
that same task (see backend/CLAUDE.md): a model missing from this list won't
register on ``Base.metadata`` and will silently drop out of autogenerate
diffs.
"""

from app.db.models.user import User
from app.db.models.status import Status
from app.db.models.service_request import ServiceRequest
from app.db.models.status_history import StatusHistory
from app.db.models.comment import Comment
from app.db.models.refresh_token import RefreshToken

__all__ = [
    "User",
    "Status",
    "ServiceRequest",
    "StatusHistory",
    "Comment",
    "RefreshToken",
]
