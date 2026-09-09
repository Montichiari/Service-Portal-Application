"""Schema contract test for the ``comments`` table (app/db/models/comment.py).

Task 6 / R10 category 3 — the RESTRICT rule on the *author* side:
``comments.author_id`` is ON DELETE RESTRICT (R8), so a user who has authored a
comment cannot be deleted out from under it.
"""

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.db.models import Comment, User


def test_delete_comment_author_is_restricted(
    db_session, make_user, make_service_request
):
    requestor = make_user()
    author = make_user()
    request = make_service_request(requestor)

    db_session.add(
        Comment(
            service_request_id=request.id, author_id=author.id, body="hello"
        )
    )
    db_session.flush()

    # Core DELETE so the database's ON DELETE RESTRICT is what's exercised.
    with pytest.raises(IntegrityError):
        db_session.execute(delete(User).where(User.id == author.id))
