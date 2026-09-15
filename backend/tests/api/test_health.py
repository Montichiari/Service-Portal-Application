"""DO-22 / T-DO-0: the deployment's health probe.

``GET /health`` is the endpoint the ALB target group polls and the pipeline
smoke-tests (DO-15), so the property that matters is not "it answers" — it is
**it does not answer 200 when the database is out of reach**. A probe that is
wrong in that direction reports a broken deploy as healthy, which is worse than
having no probe at all: the failure resurfaces later, on a user's request,
detached from the deploy that caused it.

So the suite here is weighted almost entirely toward the failure path, and the
failure path is exercised three ways, because a handler can wrongly answer 200
for three different reasons:

1. **The database is genuinely unreachable** — a real engine pointed at a dead
   port, producing a real ``psycopg2`` error through SQLAlchemy. This is the
   one that catches the biggest mutation of all: deleting the round-trip.
2. **The driver raised nothing but returned nothing** — a session stub, because
   a live Postgres cannot be made to answer ``SELECT 1`` with no row. This is
   what makes ``scalar_one()`` load-bearing rather than decorative; without it
   the handler would trust "no exception" and report healthy.
3. **The driver answered, with the wrong thing.** Same reasoning one step
   further along.

And one test in the other direction: a non-``SQLAlchemyError`` must *not* be
laundered into a tidy 503. It is not a database verdict, and reporting it as
one would hide a real bug behind an operational-looking status with nothing in
the log.

The stubs in (2) and (3) are deliberate exceptions to this project's
real-Postgres rule (backend/CLAUDE.md, "Testing"). The rule exists because a
fake database accepts values the real schema rejects — it is about the
*database's* behaviour. These two tests are about the *handler's* behaviour
when handed a degenerate result, which is a state no correctly-functioning
Postgres will ever produce on demand. (1) stays real for exactly that reason:
the realistic failure is tested against the realistic error.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import ACCESS_COOKIE_NAME
from app.database import get_db
from app.main import create_app

HEALTHY_BODY = {"status": "ok", "db": "connected"}
UNREACHABLE_BODY = {"status": "error", "db": "unreachable"}

# A connection string that cannot resolve to a server: a high loopback port
# nothing listens on refuses immediately, so the test costs a round trip to
# nowhere rather than a connect timeout. Distinctive rather than a round number
# for the same reason the credentials below are — it has to be searchable in a
# response body without matching by accident.
#
# Every field is a distinctive nonsense token rather than the real dev
# credentials, so `test_the_unreachable_body_leaks_no_connection_detail` is
# asserting something specific. Searching the response for the literal string
# "portal" would pass trivially against a body that said nothing at all.
BROKEN_DB_USER = "healthprobe-leak-user"
BROKEN_DB_PASSWORD = "healthprobe-leak-password"
BROKEN_DB_NAME = "healthprobe-leak-database"
BROKEN_DB_HOST = "127.0.0.1"
BROKEN_DB_PORT = "59137"
BROKEN_DATABASE_URL = (
    f"postgresql+psycopg2://{BROKEN_DB_USER}:{BROKEN_DB_PASSWORD}"
    f"@{BROKEN_DB_HOST}:{BROKEN_DB_PORT}/{BROKEN_DB_NAME}"
)

# Fragments of a driver error or a traceback. None may appear in the body of an
# endpoint that anyone on the internet can call without credentials.
INTERNAL_DETAIL_MARKERS = (
    BROKEN_DB_USER,
    BROKEN_DB_PASSWORD,
    BROKEN_DB_NAME,
    BROKEN_DB_HOST,
    BROKEN_DB_PORT,
    "postgresql",
    "psycopg2",
    "OperationalError",
    "Traceback",
    "sqlalchemy",
    "SELECT 1",
    ".py",
)


def _client_with_db(session_factory, **client_kwargs: Any) -> TestClient:
    """A real ``create_app()`` whose ``get_db`` yields what the test supplies.

    Built through the factory rather than assembled here, so the middleware and
    exception handlers are the ones the server actually runs — a hand-rolled
    app would let this suite pass while the served ``/health`` behaved
    differently (backend/CLAUDE.md, "App construction").
    """
    app: FastAPI = create_app()
    app.dependency_overrides[get_db] = session_factory
    return TestClient(app, **client_kwargs)


# --- The healthy path --------------------------------------------------------


def test_health_returns_200_and_no_auth_is_required(client: TestClient) -> None:
    """DO-22's first acceptance line, against a real database session.

    No cookie, no ``X-Requested-With``: the ALB target group sends neither, and
    an ECS task that only reports healthy to an authenticated caller never
    reports healthy at all.
    """
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == HEALTHY_BODY


def test_a_garbage_session_cookie_does_not_change_the_answer(
    client: TestClient,
) -> None:
    """The probe must not so much as look at credentials.

    A route that reads the cookie opportunistically would start answering 401
    the day a monitoring agent sent a stale one — the specific way "no auth
    required" regresses in practice, since nobody re-tests an endpoint whose
    unauthenticated case still works.
    """
    response = client.get(
        "/health", headers={"Cookie": f"{ACCESS_COOKIE_NAME}=not-a-real-token"}
    )

    assert response.status_code == 200
    assert response.json() == HEALTHY_BODY


# --- Failure 1: the database is genuinely unreachable ------------------------


@pytest.fixture
def unreachable_db_client() -> Iterator[TestClient]:
    """A client whose ``get_db`` yields a session bound to a dead server.

    A real engine and a real driver, not a mock: the error that reaches the
    handler is the same ``sqlalchemy.exc.OperationalError`` wrapping the same
    ``psycopg2`` failure a container with a wrong ``DATABASE_URL`` would
    produce. Nothing connects at ``sessionmaker()`` or ``Session()`` time —
    psycopg2 connects lazily — so the failure lands where it does in
    production: inside the handler's ``execute``, not during dependency
    resolution.
    """
    engine = create_engine(BROKEN_DATABASE_URL, pool_pre_ping=True, future=True)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def _get_broken_db() -> Iterator[Session]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    client = _client_with_db(_get_broken_db)
    try:
        yield client
    finally:
        engine.dispose()


def test_health_returns_503_when_the_database_is_unreachable(
    unreachable_db_client: TestClient,
) -> None:
    """DO-22's second acceptance line.

    This is the test the whole endpoint exists for, and the one that goes red
    if the round-trip is ever removed: with no query, a broken session raises
    nothing and the handler happily reports healthy.
    """
    response = unreachable_db_client.get("/health")

    assert response.status_code == 503
    assert response.json() == UNREACHABLE_BODY


def test_the_unreachable_body_leaks_no_connection_detail(
    unreachable_db_client: TestClient,
) -> None:
    """DO-22's third acceptance line.

    Asserted against the raw response text rather than the parsed body, so a
    detail smuggled into a header-adjacent field or an extra key is caught too.
    The driver error this suppresses genuinely contains the host, the port and
    the database name — `psycopg2`'s "could not connect to server" text names
    all three — and this endpoint has no authentication in front of it.
    """
    response = unreachable_db_client.get("/health")
    raw = response.text

    for marker in INTERNAL_DETAIL_MARKERS:
        assert marker.lower() not in raw.lower(), marker


# --- Failures 2 and 3: the driver answered, uselessly ------------------------


class _StubResult:
    def __init__(self, scalar: Any = None, raises: BaseException | None = None):
        self._scalar = scalar
        self._raises = raises

    def scalar_one(self) -> Any:
        if self._raises is not None:
            raise self._raises
        return self._scalar


class _StubSession:
    """Answers ``execute`` without touching a database.

    Records the statement so a test can prove the handler did ask for
    something, rather than inferring it from the absence of an exception.
    """

    def __init__(self, result: Any = None, execute_raises: BaseException | None = None):
        self.result = result
        self.execute_raises = execute_raises
        self.statements: list[str] = []

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        self.statements.append(str(statement))
        if self.execute_raises is not None:
            raise self.execute_raises
        return self.result

    def close(self) -> None:  # pragma: no cover - nothing to release
        pass


def _stub_client(session: _StubSession, **client_kwargs: Any) -> TestClient:
    return _client_with_db(lambda: session, **client_kwargs)


def test_a_round_trip_that_returns_no_row_is_not_healthy() -> None:
    """``scalar_one()`` is load-bearing, not decoration.

    ``Session.execute`` returning without raising is not the same claim as "the
    database answered". Drop the ``scalar_one()`` call and this test is the only
    thing that goes red — every other failure test here works by making
    ``execute`` itself raise, which it still would.
    """
    session = _StubSession(result=_StubResult(raises=NoResultFound("no row")))
    response = _stub_client(session).get("/health")

    assert response.status_code == 503
    assert response.json() == UNREACHABLE_BODY
    # Non-vacuous: prove the handler actually asked, so this can't pass because
    # some earlier guard short-circuited before any query was attempted.
    assert session.statements == ["SELECT 1"]


def test_a_round_trip_that_returns_the_wrong_value_is_not_healthy() -> None:
    """The comparison against ``1`` is load-bearing too.

    Same shape as the test above, one step further along: here the driver
    produced a row and it was the wrong row. Delete the ``answer != 1`` branch
    and only this test notices.
    """
    session = _StubSession(result=_StubResult(scalar=0))
    response = _stub_client(session).get("/health")

    assert response.status_code == 503
    assert response.json() == UNREACHABLE_BODY
    assert session.statements == ["SELECT 1"]


# --- The other direction: a bug is not an outage -----------------------------


def test_a_non_database_error_is_a_500_envelope_not_a_503() -> None:
    """The narrow ``except`` is a decision, so it gets a test.

    Widening it to ``except Exception`` would make every bug inside this
    handler — and anything the session raised that wasn't a driver error —
    render as a calm, unlogged "database unreachable". Operationally that is
    the worst of both worlds: the on-call reading the probe chases a database
    that is fine, and XC-14's traceback, the only record of what actually
    broke, was never written. A non-``SQLAlchemyError`` must fall through to
    the catch-all instead.
    """
    session = _StubSession(execute_raises=RuntimeError("not a database problem"))
    response = _stub_client(session, raise_server_exceptions=False).get("/health")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "not a database problem" not in response.text


# --- The consolidation itself ------------------------------------------------


def test_there_is_no_second_health_route(client: TestClient) -> None:
    """``/health/db`` was folded into ``/health`` by T-DO-0 and must stay gone.

    Not pedantry about a dead path: the thing being prevented is a
    memory-only ``/health`` coming back beside the real one, which is how an
    ALB ends up polling the probe that cannot fail. A 404 here says the DB
    check is the only health answer this service gives.
    """
    response = client.get("/health/db")

    assert response.status_code == 404
