"""Schema contract tests for the ``users`` table (app/db/models/user.py).

Covers, from Task 6 / R10:

* category 1 — CHECK constraint enforcement: an out-of-range ``role`` is
  rejected by the database with ``IntegrityError`` (proves ``ck_users_role_valid``
  is actually enforced, not just declared on the model).
* category 3 — ON DELETE RESTRICT: a user who is a request's ``requestor``
  cannot be deleted.
* category 3 — ON DELETE SET NULL: deleting a user who is a request's
  ``assignee`` nulls ``assignee_id`` rather than blocking the delete.
"""

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.db.models import ServiceRequest, User


def test_role_check_constraint_rejects_out_of_range(db_session, make_user):
    # ck_users_role_valid: role IN ('user', 'admin'). Any other value must be
    # rejected by Postgres itself on INSERT.
    with pytest.raises(IntegrityError):
        make_user(role="superuser")  # factory flushes -> INSERT -> CheckViolation


def test_delete_requestor_is_restricted(
    db_session, make_user, make_service_request
):
    requestor = make_user()
    make_service_request(requestor)

    # Core DELETE (not Session.delete) so the database's ON DELETE RESTRICT
    # rule is what's under test, not SQLAlchemy's in-Python cascade handling.
    with pytest.raises(IntegrityError):
        db_session.execute(delete(User).where(User.id == requestor.id))


def test_delete_assignee_sets_request_assignee_id_null(
    db_session, make_user, make_service_request
):
    requestor = make_user()
    assignee = make_user()
    request = make_service_request(requestor, assignee=assignee)
    request_id = request.id

    db_session.execute(delete(User).where(User.id == assignee.id))
    db_session.expire_all()

    reloaded = db_session.get(ServiceRequest, request_id)
    assert reloaded is not None, "SET NULL must not delete the request"
    assert reloaded.assignee_id is None
    assert reloaded.requestor_id == requestor.id  # untouched
