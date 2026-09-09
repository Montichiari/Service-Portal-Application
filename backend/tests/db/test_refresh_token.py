"""Schema contract test for the ``refresh_tokens`` table
(app/db/models/refresh_token.py).

Task 6 / R10 category 3 — the CASCADE rule on the token side:
``refresh_tokens.user_id`` is ON DELETE CASCADE (R8), so deleting the owning
user removes their refresh tokens.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from app.db.models import RefreshToken, User


def test_delete_user_cascades_refresh_tokens(db_session, make_user):
    user = make_user()
    token = RefreshToken(
        user_id=user.id,
        token_hash="hashed-token",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(token)
    db_session.flush()
    token_id = token.id
    user_id = user.id

    db_session.execute(delete(User).where(User.id == user_id))
    db_session.expire_all()

    assert db_session.get(RefreshToken, token_id) is None
    assert (
        db_session.execute(
            select(func.count())
            .select_from(RefreshToken)
            .where(RefreshToken.user_id == user_id)
        ).scalar_one()
        == 0
    )
