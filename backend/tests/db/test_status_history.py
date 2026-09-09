"""Schema contract test for the ``status_history`` table
(app/db/models/status_history.py).

Task 6 / R10 category 3 — the SET NULL rule on the *actor* side: ``changed_by_id``
is a nullable FK with ON DELETE SET NULL (R5 / R8), so deleting the acting user
leaves the immutable history row in place with ``changed_by_id`` cleared.
"""

from sqlalchemy import delete

from app.db.models import StatusHistory, User


def test_delete_actor_sets_changed_by_id_null(
    db_session, make_user, make_service_request
):
    requestor = make_user()
    actor = make_user()
    request = make_service_request(requestor)

    history = StatusHistory(
        service_request_id=request.id,
        status_id=request.current_status_id,
        changed_by_id=actor.id,
    )
    db_session.add(history)
    db_session.flush()
    history_id = history.id

    db_session.execute(delete(User).where(User.id == actor.id))
    db_session.expire_all()

    reloaded = db_session.get(StatusHistory, history_id)
    assert reloaded is not None, "SET NULL must not delete the history row"
    assert reloaded.changed_by_id is None
