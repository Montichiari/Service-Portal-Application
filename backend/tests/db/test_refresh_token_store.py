"""Refresh-token storage helpers from app/core/security.py, against real Postgres.

Lives under tests/db/ rather than alongside tests/core/test_security.py because
these helpers take a ``Session``: they need the ``db_session`` / ``make_user``
fixtures from this package's conftest, and per backend/CLAUDE.md the suite runs
against a real Postgres database, never SQLite. Every test rolls back at
teardown.

The pure (database-free) half of the module is covered in
tests/core/test_security.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.security import (
    REFRESH_TOKEN_TTL,
    find_refresh_token,
    hash_refresh_token,
    is_refresh_token_active,
    issue_refresh_token,
)
from app.db.models import RefreshToken


def test_issue_refresh_token_persists_only_the_hash(db_session, make_user):
    """backend/CLAUDE.md: the raw token is never stored — only its hash."""
    user = make_user()

    raw_token, token = issue_refresh_token(db_session, user.id)

    assert token.id is not None  # flushed, server default populated
    assert token.user_id == user.id
    assert token.token_hash == hash_refresh_token(raw_token)
    assert token.revoked_at is None

    # And nothing anywhere in the row echoes the raw token.
    stored = db_session.execute(
        select(RefreshToken).where(RefreshToken.id == token.id)
    ).scalar_one()
    assert raw_token not in str(stored.token_hash)
    assert (
        db_session.execute(
            select(func.count())
            .select_from(RefreshToken)
            .where(RefreshToken.token_hash == raw_token)
        ).scalar_one()
        == 0
    )


def test_issued_token_expires_30_days_out(db_session, make_user):
    """AUTH-6 / design.md §1: 30 day refresh lifetime."""
    user = make_user()
    now = datetime.now(timezone.utc)

    _, token = issue_refresh_token(db_session, user.id, now=now)

    assert token.expires_at == now + REFRESH_TOKEN_TTL
    assert REFRESH_TOKEN_TTL == timedelta(days=30)


def test_find_refresh_token_round_trips_the_raw_token(db_session, make_user):
    user = make_user()
    raw_token, token = issue_refresh_token(db_session, user.id)

    found = find_refresh_token(db_session, raw_token)

    assert found is not None
    assert found.id == token.id
    assert is_refresh_token_active(found) is True


def test_find_refresh_token_returns_none_for_an_unknown_token(db_session, make_user):
    make_user()

    assert find_refresh_token(db_session, "a-token-that-was-never-issued") is None


def test_find_refresh_token_still_returns_a_revoked_row(db_session, make_user):
    """AUTH-11 depends on telling "rotated out" apart from "never existed" —
    a lookup that filtered revoked rows would collapse the two and make
    token-family revocation on replay impossible to implement."""
    user = make_user()
    raw_token, token = issue_refresh_token(db_session, user.id)
    token.revoked_at = datetime.now(timezone.utc)
    db_session.flush()

    found = find_refresh_token(db_session, raw_token)

    assert found is not None
    assert found.id == token.id
    assert is_refresh_token_active(found) is False


def test_expired_token_is_found_but_not_active(db_session, make_user):
    user = make_user()
    issued = datetime.now(timezone.utc) - REFRESH_TOKEN_TTL - timedelta(days=1)
    raw_token, _ = issue_refresh_token(db_session, user.id, now=issued)

    found = find_refresh_token(db_session, raw_token)

    assert found is not None
    assert found.revoked_at is None  # not revoked — just past its expiry
    assert is_refresh_token_active(found) is False


def test_each_issued_token_is_distinct(db_session, make_user):
    """Two logins by the same user produce two independent, separately
    revocable rows — the precondition for AUTH-11's family revocation."""
    user = make_user()

    first_raw, first = issue_refresh_token(db_session, user.id)
    second_raw, second = issue_refresh_token(db_session, user.id)

    assert first_raw != second_raw
    assert first.id != second.id
    assert first.token_hash != second.token_hash
    assert find_refresh_token(db_session, first_raw).id == first.id
    assert find_refresh_token(db_session, second_raw).id == second.id


def test_tokens_are_scoped_to_their_own_user(db_session, make_user):
    alice = make_user()
    bob = make_user()
    alice_raw, _ = issue_refresh_token(db_session, alice.id)
    issue_refresh_token(db_session, bob.id)

    found = find_refresh_token(db_session, alice_raw)

    assert found.user_id == alice.id
    assert found.user_id != bob.id


def test_issue_refresh_token_does_not_commit(db_session, make_user):
    """The caller owns the transaction boundary — the helper only flushes, so a
    failed request can still roll the token back with the rest of its work."""
    user = make_user()

    _, token = issue_refresh_token(db_session, user.id)
    token_id = token.id
    db_session.rollback()

    assert db_session.get(RefreshToken, token_id) is None


def test_is_refresh_token_active_boundary(db_session, make_user):
    """Exactly-at-expiry counts as expired, not active."""
    user = make_user()
    now = datetime.now(timezone.utc)
    _, token = issue_refresh_token(db_session, user.id, now=now)
    expiry = now + REFRESH_TOKEN_TTL

    assert is_refresh_token_active(token, now=expiry - timedelta(seconds=1)) is True
    assert is_refresh_token_active(token, now=expiry) is False
    assert is_refresh_token_active(token, now=expiry + timedelta(seconds=1)) is False


def test_issued_token_cascades_with_its_user(db_session, make_user):
    """Sanity check that the helper's rows obey the same CASCADE as hand-built
    ones (R8) — nothing about going through security.py changes that."""
    user = make_user()
    _, token = issue_refresh_token(db_session, user.id)
    token_id = token.id

    db_session.delete(user)
    db_session.flush()
    db_session.expire_all()

    assert db_session.get(RefreshToken, token_id) is None


def test_hash_lookup_is_not_vulnerable_to_a_uuid_lookalike(db_session, make_user):
    """A caller can't fish a row out by presenting something that merely looks
    like a token id."""
    user = make_user()
    _, token = issue_refresh_token(db_session, user.id)

    assert find_refresh_token(db_session, str(token.id)) is None
    assert find_refresh_token(db_session, token.token_hash) is None
    assert find_refresh_token(db_session, str(uuid.uuid4())) is None
