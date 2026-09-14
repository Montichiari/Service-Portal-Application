"""ASGI entrypoint.

``create_app()`` is where the cross-cutting wiring from T-AUTH-2 is applied —
the error-envelope handlers and the CSRF middleware — so that the tests can
build a byte-identical app and hang throwaway routes off it. Configuring the
module-level ``app`` in place instead would leave the tested app and the served
app free to drift apart.
"""

from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.errors import register_exception_handlers
from app.api.middleware import register_middleware
from app.api.openapi import use_corrected_openapi
from app.api.routes.auth import router as auth_router
from app.api.routes.chat import router as chat_router
from app.api.routes.comments import router as comments_router
from app.api.routes.service_requests import router as service_requests_router
from app.api.routes.status_changes import router as status_changes_router
from app.api.routes.statuses import router as statuses_router
from app.database import get_db

# XC-1. Applied once, here, so no route path spells it out for itself
# (backend/CLAUDE.md).
API_V1_PREFIX = "/api/v1"

health_router = APIRouter(tags=["health"])


# The only response in the API that is *not* the error envelope: this one is
# built by the handler as a plain JSONResponse rather than raised, so it never
# reaches `register_exception_handlers`. Declared with its own content so that
# `app/api/openapi.py` leaves it alone — documenting it as an envelope would be
# the same class of untruth this task exists to fix.
DB_UNREACHABLE_RESPONSE = {
    "description": "Returned when the database cannot be reached.",
    "content": {
        "application/json": {
            "schema": {
                "type": "object",
                "required": ["status", "db"],
                "properties": {
                    "status": {"type": "string", "enum": ["error"]},
                    "db": {"type": "string", "enum": ["unreachable"]},
                },
            },
            "example": {"status": "error", "db": "unreachable"},
        }
    },
}


@health_router.get("/health", summary="Liveness probe")
def health() -> dict[str, str]:
    return {"status": "ok"}


@health_router.get(
    "/health/db",
    summary="Database connectivity probe",
    responses={503: DB_UNREACHABLE_RESPONSE},
)
def health_db(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "db": "unreachable"},
        )
    return {"status": "ok", "db": "connected"}


def create_app() -> FastAPI:
    app = FastAPI(title="Service Portal API")
    register_exception_handlers(app)
    register_middleware(app)
    # Liveness probes, deliberately outside /api/v1 (XC-1 governs the API
    # surface; these are operational endpoints, not part of the contract).
    app.include_router(health_router)
    # Resource routers, each carrying its own resource prefix.
    app.include_router(auth_router, prefix=API_V1_PREFIX)
    app.include_router(statuses_router, prefix=API_V1_PREFIX)
    app.include_router(service_requests_router, prefix=API_V1_PREFIX)
    # Mounted after its parent resource. Its paths nest under
    # `/service-requests/{request_id}`, and `/service-requests/{request_id}`
    # itself is a real route — registering the sub-resource first would put a
    # more general pattern ahead of a more specific one in the route table.
    app.include_router(comments_router, prefix=API_V1_PREFIX)
    # The second sub-resource, mounted for the same reason and after it.
    app.include_router(status_changes_router, prefix=API_V1_PREFIX)
    # Its own resource family, unrelated to the three above: no path
    # parameters, and its two routes address the caller's own conversation
    # (specs/chatbot/design.md §8), so ordering against the service-request
    # routes cannot matter either way.
    app.include_router(chat_router, prefix=API_V1_PREFIX)
    # Last, because it introspects the mounted routes to document the auth,
    # CSRF and error-envelope behaviour that lives in the wiring above rather
    # than in any route signature (T-DOCS-0). Documentation only — it reads the
    # app and changes nothing the app serves.
    use_corrected_openapi(app)
    return app


app = create_app()
