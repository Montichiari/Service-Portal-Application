"""Schema contract tests for the ``service_requests`` table
(app/db/models/service_request.py).

Covers, from Task 6 / R10:

* category 1 — CHECK constraint enforcement: an out-of-range ``priority`` is
  rejected by the database with ``IntegrityError``.
* category 2 — dual-FK disambiguation: ``requestor`` and ``assignee`` resolve
  to the correct, distinct ``users.id`` values (not merely non-``None``).
* category 3 — ON DELETE CASCADE: deleting a request removes its
  ``status_history`` and ``comments`` rows.
* R4 — ``request_metadata`` server-defaults to an empty JSONB object.
"""

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.db.models import Comment, ServiceRequest, StatusHistory


def test_priority_check_constraint_rejects_out_of_range(
    db_session, make_user, make_service_request
):
    # ck_service_requests_priority_valid: priority IN ('low', 'medium', 'high').
    requestor = make_user()
    with pytest.raises(IntegrityError):
        make_service_request(requestor, priority="urgent")


def test_requestor_and_assignee_resolve_to_distinct_users(
    db_session, make_user, make_service_request
):
    # A misconfigured dual-FK relationship fails at mapper-configuration time
    # and can pass a casual code read — so assert on the resolved id values.
    requestor = make_user(first_name="Rae", last_name="Questor")
    assignee = make_user(first_name="Ash", last_name="Signee")
    request = make_service_request(requestor, assignee=assignee)
    request_id = request.id

    # Clear the identity map so the relationships below are read back out of
    # the database rather than out of the pending unit of work.
    db_session.expire_all()
    loaded = db_session.get(ServiceRequest, request_id)

    assert requestor.id != assignee.id
    assert loaded.requestor_id == requestor.id
    assert loaded.assignee_id == assignee.id
    assert loaded.requestor.id == requestor.id
    assert loaded.assignee.id == assignee.id
    assert loaded.requestor.id != loaded.assignee.id


def test_delete_request_cascades_to_history_and_comments(
    db_session, make_user, make_service_request
):
    requestor = make_user()
    author = make_user()
    request = make_service_request(requestor)

    history = StatusHistory(
        service_request_id=request.id,
        status_id=request.current_status_id,
        changed_by_id=requestor.id,
        note="opened",
    )
    comment = Comment(
        service_request_id=request.id, author_id=author.id, body="on it"
    )
    db_session.add_all([history, comment])
    db_session.flush()
    request_id, history_id, comment_id = request.id, history.id, comment.id

    db_session.execute(
        delete(ServiceRequest).where(ServiceRequest.id == request_id)
    )
    db_session.expire_all()

    assert db_session.get(StatusHistory, history_id) is None
    assert db_session.get(Comment, comment_id) is None
    assert (
        db_session.execute(
            select(func.count())
            .select_from(StatusHistory)
            .where(StatusHistory.service_request_id == request_id)
        ).scalar_one()
        == 0
    )
    assert (
        db_session.execute(
            select(func.count())
            .select_from(Comment)
            .where(Comment.service_request_id == request_id)
        ).scalar_one()
        == 0
    )


def test_request_metadata_server_defaults_to_empty_object(
    db_session, make_user, make_service_request
):
    requestor = make_user()
    request = make_service_request(requestor)  # no request_metadata passed
    db_session.expire_all()

    reloaded = db_session.get(ServiceRequest, request.id)
    assert reloaded.request_metadata == {}
