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
from app.database import get_db

health_router = APIRouter(tags=["health"])


@health_router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@health_router.get("/health/db")
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
    # Resource routers mount here with their /api/v1 prefix from T-AUTH-3 on.
    return app


app = create_app()
