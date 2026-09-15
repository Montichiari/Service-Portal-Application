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


# --- GET /health (DO-22) -----------------------------------------------------
#
# One probe, not two. Until T-DO-0 this was a pair: a `/health` that returned
# `{"status": "ok"}` from process memory alone, and a `/health/db` that
# queried. DO-22 gives `/health` to both the ALB target group and the
# pipeline's smoke test (DO-15), and a probe that answers 200 from a container
# whose connection string is wrong is worse than no probe — it reports the
# deploy healthy and defers the failure to the first real request. The
# memory-only variant had no remaining caller, so it is gone rather than kept
# as a second answer to the same question.

# The two response bodies are declared rather than inferred, because neither is
# what FastAPI would derive on its own. The 503 is the only response in the API
# that is *not* the error envelope: it is built by the handler as a plain
# JSONResponse rather than raised, so it never reaches
# `register_exception_handlers`, and declaring it with content is what makes
# `app/api/openapi.py` leave it alone — documenting it as an envelope would be
# the same class of untruth that pass exists to fix. The 200 is declared beside
# it so the document says what the probe actually answers, rather than the
# shapeless `additionalProperties` a `dict[str, str]` return annotation would
# produce, and so the pair reads as the two halves of one contract.
DB_CONNECTED_RESPONSE = {
    "description": "Returned when a database round-trip succeeded.",
    "content": {
        "application/json": {
            "schema": {
                "type": "object",
                "required": ["status", "db"],
                "properties": {
                    "status": {"type": "string", "enum": ["ok"]},
                    "db": {"type": "string", "enum": ["connected"]},
                },
            },
            "example": {"status": "ok", "db": "connected"},
        }
    },
}

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


def _unreachable() -> JSONResponse:
    """A fresh 503, never a shared module-level instance.

    A `Response` object carries mutable headers that middleware may add to on
    the way out, so one instance reused across requests is a cross-request
    mutation waiting to happen.
    """
    return JSONResponse(
        status_code=503, content={"status": "error", "db": "unreachable"}
    )


@health_router.get(
    "/health",
    summary="Liveness and database-connectivity probe",
    responses={200: DB_CONNECTED_RESPONSE, 503: DB_UNREACHABLE_RESPONSE},
)
def health(db: Session = Depends(get_db)):
    """Unauthenticated probe. 200 only if a live database round-trip succeeds."""
    # `Session.execute` returning without raising is not the same claim as "the
    # database answered": a later edit that swapped the statement, stubbed the
    # session or dropped the query would leave this handler reporting healthy
    # while proving nothing. `scalar_one()` forces the row out of the cursor
    # and raises if there isn't exactly one, which collapses "no exception" and
    # "the database answered" into the same statement. The value comparison
    # below closes the last gap — a row that isn't the one we asked for.
    try:
        answer = db.execute(text("SELECT 1")).scalar_one()
    except SQLAlchemyError:
        # `exc` is deliberately not rendered into the body (DO-22's third
        # acceptance line): a driver error's text names the host, port, user
        # and database it failed to reach, and this endpoint has no
        # authentication in front of it.
        #
        # The except is equally deliberately narrow. `SQLAlchemyError` covers
        # every connection, authentication and query failure the driver raises
        # through SQLAlchemy — the realistic unreachable-database cases.
        # Anything outside that family is not a database verdict and must not
        # be reported as one: it falls through to XC-14's catch-all, which is
        # still a non-200 answer to the probe *and* logs the traceback, where a
        # broad `except Exception` here would swallow a genuine bug into a
        # tidy, unlogged 503.
        return _unreachable()
    if answer != 1:
        return _unreachable()
    return {"status": "ok", "db": "connected"}


def create_app() -> FastAPI:
    app = FastAPI(title="Service Portal API")
    register_exception_handlers(app)
    register_middleware(app)
    # The health probe, deliberately outside /api/v1 (XC-1 governs the API
    # surface; this is an operational endpoint, not part of the contract).
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
