"""Fixtures for the API-layer tests (T-AUTH-2).

T-AUTH-2 builds cross-cutting machinery and, per its acceptance criteria, adds
no auth endpoints — so there is nothing real yet to hang it on. The throwaway
routes below fill that gap. They live here, in the test package, rather than in
``app/``: shipping a ``/__test__/boom`` route that deliberately crashes, or an
unauthenticated echo endpoint, is not something that should be one forgotten
cleanup away from being served in production.

They are mounted on an app built by the real ``create_app()``, so the handlers
and middleware under test are the exact ones ``app.main:app`` serves. A
hand-assembled test app could pass while the served app was wired differently.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime

import pytest
from fastapi import APIRouter, Depends, FastAPI, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.deps import get_current_user, require_role
from app.api.middleware import CSRF_HEADER
from app.core.security import ACCESS_COOKIE_NAME, create_access_token
from app.database import get_db
from app.db.models import User
from app.main import create_app

TEST_PREFIX = "/api/v1/__test__"

# Sent on every non-GET call that isn't specifically testing XC-9's rejection.
CSRF_HEADERS = {CSRF_HEADER: "XMLHttpRequest"}

# Distinctive strings planted in the four places an unhandled exception can
# come from (XC-14's "anywhere while processing a request"). Each one stands in
# for something that must never reach a client — a connection string, a
# password hash serialized out of an ORM row. A test asserting the response
# doesn't contain them is asserting the real property, not a paraphrase of it.
ROUTE_LEAK = "route-secret-hunter2"
DEPENDENCY_LEAK = "postgres://portal:dependency-secret-hunter2@db/portal"
SERIALIZATION_LEAK = "serialization-secret-hunter2"
MIDDLEWARE_LEAK = "middleware-secret-hunter2"

# Header that triggers the exploding middleware in `exploding_middleware_app`.
EXPLODE_HEADER = "X-Explode"


class EchoTag(BaseModel):
    name: str = Field(min_length=1)


class EchoBody(BaseModel):
    title: str = Field(min_length=1, max_length=10)
    # Nested + indexed, so the `fields` keys for list items are exercised and
    # not just the flat single-level case.
    tags: list[EchoTag] = Field(default_factory=list)


class BoomPayload(BaseModel):
    value: int


def _exploding_dependency() -> None:
    raise RuntimeError(DEPENDENCY_LEAK)


def _build_test_router() -> APIRouter:
    router = APIRouter(prefix=TEST_PREFIX)

    @router.get("/open")
    def open_route() -> dict[str, bool]:
        return {"ok": True}

    @router.get("/protected")
    def protected(user: User = Depends(get_current_user)) -> dict[str, str]:
        return {"id": str(user.id), "role": user.role}

    @router.post("/protected")
    def protected_post(user: User = Depends(get_current_user)) -> dict[str, str]:
        return {"id": str(user.id), "role": user.role}

    @router.get("/admin")
    def admin_only(user: User = Depends(require_role("admin"))) -> dict[str, str]:
        return {"id": str(user.id), "role": user.role}

    @router.get("/user-or-above")
    def user_or_above(user: User = Depends(require_role("user"))) -> dict[str, str]:
        return {"id": str(user.id), "role": user.role}

    @router.post("/echo")
    def echo(
        body: EchoBody, limit: int = Query(default=1)
    ) -> dict[str, object]:
        return {"title": body.title, "limit": limit}

    # --- XC-14: the four places an unhandled exception can originate ---------

    @router.get("/boom")
    def boom() -> None:
        raise RuntimeError(ROUTE_LEAK)

    @router.get("/boom-dependency", dependencies=[Depends(_exploding_dependency)])
    def boom_dependency() -> dict[str, bool]:
        # Never reached. A dependency raising is the realistic case once real
        # routes exist — `get_current_user`'s query failing mid-request.
        return {"ok": True}

    @router.get("/boom-serialization", response_model=BoomPayload)
    def boom_serialization():
        # Fails *after* the handler returns, when FastAPI validates the
        # response — a different code path from a handler that raises, and the
        # one that matters most for leaks: the exception FastAPI raises here
        # carries the offending value, which in a real route is whatever the
        # response model was meant to keep out of the payload.
        return {"value": SERIALIZATION_LEAK}

    return router


@pytest.fixture
def api_app(db_session: Session) -> Iterator[FastAPI]:
    """A real ``create_app()`` with the throwaway router and a test DB session.

    ``get_db`` is overridden with the transaction-wrapped ``db_session`` so
    that rows a test creates are visible to the request handler and everything
    still rolls back at teardown.
    """
    app = create_app()
    app.include_router(_build_test_router())
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client(api_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(api_app) as test_client:
        yield test_client


@pytest.fixture
def auth_client(api_app: FastAPI) -> Iterator[TestClient]:
    """A cookie-persisting client for whole auth flows (T-AUTH-3).

    ``base_url`` is **https** deliberately. The auth cookies are ``Secure``,
    and httpx's cookie jar silently declines to store a Secure cookie received
    over ``http`` — so a login would appear to succeed and the very next call
    would 401, looking exactly like broken auth rather than a misconfigured
    test client. tasks.md flags this for this task specifically; it is cheaper
    to get right than to debug.

    ``X-Requested-With`` is sent by default so flow tests read as flows rather
    than as a header repeated on every line. That does not weaken XC-9:
    ``test_csrf.py`` covers the check on its own, through the plain ``client``
    fixture, including on paths that route nowhere.
    """
    with TestClient(
        api_app, base_url="https://testserver", headers=CSRF_HEADERS
    ) as test_client:
        yield test_client


@pytest.fixture
def raw_client(api_app: FastAPI) -> Iterator[TestClient]:
    """A client that returns the 500 response instead of re-raising.

    Starlette's ``ServerErrorMiddleware`` re-raises an unhandled exception
    after the handler has produced its response, so the default client would
    surface the ``RuntimeError`` rather than let a test assert on the envelope
    the client would actually receive.
    """
    with TestClient(api_app, raise_server_exceptions=False) as test_client:
        yield test_client


class ExplodingMiddleware(BaseHTTPMiddleware):
    """Raises from inside the middleware stack, on demand.

    Exists to prove the catch-all handler sits *outside* the user middleware
    stack rather than inside it. That placement is easy to break by accident
    when middleware is added or reordered — T-AUTH-3 adds CORS — and the
    failure mode is a bare Starlette fallback response instead of the
    envelope.
    """

    async def dispatch(self, request, call_next):
        if request.headers.get(EXPLODE_HEADER):
            raise RuntimeError(MIDDLEWARE_LEAK)
        return await call_next(request)


@pytest.fixture
def exploding_middleware_client(db_session: Session) -> Iterator[TestClient]:
    app = create_app()
    app.include_router(_build_test_router())
    app.dependency_overrides[get_db] = lambda: db_session
    app.add_middleware(ExplodingMiddleware)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def client_for(api_app: FastAPI, cookie_header) -> Callable[..., TestClient]:
    """A client already authenticated as a given user (T-SR-0).

    ``auth_client`` above drives whole auth *flows* — register, then login,
    then call — and its cookie jar is the point. Most resource tests don't want
    the flow; they want "as this user, GET that". This mints the access token
    directly and sends it as a plain ``Cookie`` header, which also sidesteps
    the jar's domain-scoping rules that ``replace_cookie`` in
    ``test_auth_endpoints.py`` exists to work around.

    ``raise_server_exceptions=False`` is for the one test that must observe a
    ``500`` as a response rather than as a re-raised exception (SR-14's
    atomicity check). It is opt-in because everywhere else a 500 should surface
    as a traceback, not as a quietly asserted status code.
    """

    def _client_for(user: User, *, raise_server_exceptions: bool = True) -> TestClient:
        return TestClient(
            api_app,
            # https for the same reason auth_client uses it — Secure cookies.
            base_url="https://testserver",
            headers={**CSRF_HEADERS, **cookie_header(user)},
            raise_server_exceptions=raise_server_exceptions,
        )

    return _client_for


@pytest.fixture
def cookie_header():
    """Build a ``Cookie`` header carrying an access token for ``user``.

    Set as a plain header rather than through the client's cookie jar: the
    real cookies are ``Secure``, and a jar would silently refuse to store them
    over the test client's ``http://`` base URL.
    """

    def _cookie_header(
        user: User, *, now: datetime | None = None, token: str | None = None
    ) -> dict[str, str]:
        if token is None:
            token = create_access_token(user_id=user.id, role=user.role, now=now)
        return {"Cookie": f"{ACCESS_COOKIE_NAME}={token}"}

    return _cookie_header
