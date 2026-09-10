"""Shared database fixtures for the whole test suite.

Originally ``tests/db/conftest.py``, serving the schema contract suite (Task 6
/ R10) alone. Promoted to the top level in T-AUTH-2, because the API tests
under ``tests/api/`` need ``db_session`` too — ``get_current_user`` loads a
real user row, so exercising it needs a real user in a real database.
(T-AUTH-3's task notes list this promotion as its own first step; it came due
one task earlier than expected.)

The suite runs against a **real** Postgres database — never SQLite (R10,
backend/CLAUDE.md): SQLite doesn't enforce ``CHECK`` constraints the same way
and has no ``JSONB`` type, so a green SQLite run would be validating the wrong
schema.

Fixtures defined here:

* ``_prepared_database`` (session) — creates the dedicated
  ``service_portal_test`` database if it's missing, then runs
  ``alembic upgrade head`` into it, once per test run. The suite is therefore
  self-provisioning: it never assumes someone migrated a database by hand.
  Depended on explicitly by ``engine`` and ``alembic_config`` rather than being
  autouse, so that the pure-unit suites (``tests/core/``) still run with no
  Postgres available — as autouse at this level, it would have made every test
  in the repo need a database.
* ``engine`` (session) — a ``NullPool`` engine bound to ``TEST_DATABASE_URL``.
* ``db_session`` (function) — wraps each test in an outer transaction plus a
  SAVEPOINT, both rolled back at teardown (R10). No test ever deletes rows to
  clean up after itself.
* ``alembic_config`` (function) — a fresh Alembic ``Config`` targeting the
  test database, used by the migration round-trip test.
* ``make_user`` / ``open_status`` / ``make_service_request`` — tiny row
  factories. Everything rolls back, so they need no cleanup.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Callable, Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.config import settings
from app.db.models import ServiceRequest, Status, User

# .../backend/tests/conftest.py -> parents[1] == .../backend
BACKEND_DIR = Path(__file__).resolve().parents[1]

TEST_DATABASE_URL = settings.TEST_DATABASE_URL

# Hard stop: this suite drops/recreates tables and rolls back real
# transactions. It must never be pointed at the development database.
if TEST_DATABASE_URL == settings.DATABASE_URL:
    raise RuntimeError(
        "TEST_DATABASE_URL is identical to DATABASE_URL. The schema contract "
        "suite refuses to run against the development database."
    )

# alembic/env.py picks its target from settings.DATABASE_URL. Repoint that at
# the test database for the whole process, so the programmatic
# `alembic upgrade head` below (and anything else reading settings.DATABASE_URL
# during the run — app.database's engine included) can never touch dev.
settings.DATABASE_URL = TEST_DATABASE_URL


def make_alembic_config() -> Config:
    """An Alembic ``Config`` pointed at the test database.

    Built without an ``.ini`` file on purpose: with ``config_file_name is
    None``, ``alembic/env.py`` skips its ``fileConfig()`` call, so running
    migrations from inside pytest doesn't tear down pytest's own logging.
    """
    cfg = Config()
    cfg.set_main_option("script_location", (BACKEND_DIR / "alembic").as_posix())
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return cfg


def _ensure_test_database() -> None:
    """``CREATE DATABASE service_portal_test`` if it doesn't exist yet."""
    url = make_url(TEST_DATABASE_URL)
    admin_engine = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": url.database},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="session")
def _prepared_database() -> None:
    """Provision + migrate the test database once for the whole run."""
    _ensure_test_database()
    command.upgrade(make_alembic_config(), "head")


@pytest.fixture(scope="session")
def engine(_prepared_database: None) -> Iterator[Engine]:
    eng = create_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """Per-test transaction + SAVEPOINT, both rolled back at teardown (R10).

    This is SQLAlchemy's documented "join a Session into an external
    transaction" recipe: ``connection.begin()`` opens the outer transaction,
    the ``Session`` is bound to that connection, ``connection.begin_nested()``
    opens a SAVEPOINT, and the ``after_transaction_end`` listener re-opens the
    SAVEPOINT whenever the test ends it (e.g. a flush that raised
    ``IntegrityError``). Teardown rolls back the outer transaction, so the
    database is left exactly as the migration produced it.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess: Session, trans) -> None:  # noqa: ANN001
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        event.remove(session, "after_transaction_end", _restart_savepoint)
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def alembic_config(_prepared_database: None) -> Config:
    return make_alembic_config()


# --- lightweight row factories ----------------------------------------------
# Every test is rolled back at teardown, so none of these need cleanup.


@pytest.fixture
def make_user(db_session: Session) -> Callable[..., User]:
    def _make(**overrides: object) -> User:
        fields: dict[str, object] = dict(
            email=f"user-{uuid.uuid4().hex[:12]}@example.test",
            password_hash="not-a-real-hash",
            first_name="Test",
            last_name="User",
        )
        fields.update(overrides)
        user = User(**fields)
        db_session.add(user)
        db_session.flush()
        return user

    return _make


@pytest.fixture
def open_status(db_session: Session) -> Status:
    return db_session.execute(
        select(Status).where(Status.name == "open")
    ).scalar_one()


@pytest.fixture
def make_service_request(
    db_session: Session, open_status: Status
) -> Callable[..., ServiceRequest]:
    def _make(requestor: User, **overrides: object) -> ServiceRequest:
        fields: dict[str, object] = dict(
            requestor=requestor,
            title="Printer on 3rd floor is jammed",
            description="Paper jam that will not clear.",
            current_status_id=open_status.id,
        )
        fields.update(overrides)
        request = ServiceRequest(**fields)
        db_session.add(request)
        db_session.flush()
        return request

    return _make
