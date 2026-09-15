"""Fixtures for the tests that talk to a real model (T-CHAT-1).

Not collected by ``python -m pytest`` — ``pytest.ini`` points ``testpaths`` at
``tests`` — so nothing here runs unless someone names this directory. See
``README.md`` next door for why that separation is a directory and not a
marker.

The database fixtures are **imported** from ``tests/conftest.py`` rather than
copied: the transaction-per-test recipe, the self-provisioning test database
and the row factories are subtle enough that a second implementation would
drift, and a live test running against a differently-prepared database would be
testing something other than what the suite tests. They are imported by name,
one at a time, and deliberately not with a star import — ``tests/conftest.py``
also defines the autouse fixture that unsets ``ANTHROPIC_API_KEY``, which is
precisely what these tests need left alone.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest

# Importing this module also repoints `settings.DATABASE_URL` at the test
# database for the process, which is exactly as wanted here: a live tool call
# writes a real service request, and it must not write it into the development
# database.
from tests.conftest import (  # noqa: F401 - re-exported as fixtures
    _prepared_database,
    db_session,
    engine,
    make_service_request,
    make_user,
    open_status,
)

from app.chat.anthropic_client import build_model_client
from app.chat.client import ChatModelClient, ModelClientNotConfiguredError
from app.chat.prompt import build_system_prompt
from app.chat.tools import available_tools
from app.config import settings


@pytest.fixture(scope="session")
def live_client() -> ChatModelClient:
    """The real client, built from ``.env`` — or a skip explaining why not.

    One client for the session: these are real HTTP calls and there is no
    reason to open a connection pool per test.

    A skip rather than a failure, and the only skip in this project that is
    honest: with no key configured the test did not pass and did not fail
    either, and saying so is more useful than a red run that looks like the
    assistant is broken.
    """
    try:
        return build_model_client()
    except ModelClientNotConfiguredError as exc:
        pytest.skip(f"no live model configured: {exc}")


@pytest.fixture(scope="session")
def system_prompt() -> str:
    """The prompt the application actually sends.

    Built through ``build_system_prompt`` rather than written here, because a
    prompt written for the eval would make the eval's results say nothing about
    production. This is the whole point of the tool-choice set: it measures the
    real prompt's steering.
    """
    return build_system_prompt()


@pytest.fixture(scope="session")
def tools() -> list[dict[str, Any]]:
    """Likewise the real tool definitions, descriptions and all."""
    return available_tools()


@pytest.fixture(autouse=True)
def _announce_the_model() -> Iterator[None]:
    """Print which deployment answered, so a transcript is attributable.

    A recorded transcript with no model or endpoint beside it is hard to trust
    a week later, and the two are configuration rather than code — the same run
    against a different ``.env`` is a different experiment.
    """
    print(
        f"\n[model] {settings.ANTHROPIC_MODEL} "
        f"via {settings.ANTHROPIC_BASE_URL or 'api.anthropic.com'}"
    )
    yield
