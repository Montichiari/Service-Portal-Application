"""The two status-change endpoints (T-SC-0; SC-1 .. SC-8, XC-5, XC-7, XC-10).

Contract tests against the real Postgres test database and the real
``create_app()`` (backend/CLAUDE.md) — no SQLite, no hand-assembled app.

Error assertions check the whole envelope, not the status code alone.

Four of these are written to fail for a specific reason rather than to describe
a feature, and are worth reading as such:

* ``test_transition_writes_nothing_when_the_history_insert_fails`` is what
  catches the two writes of SC-5 being split across two transactions — the
  success path cannot, because it looks identical either way.
* ``test_rejected_status_id_applies_nothing`` is the same requirement from the
  other side (SC-6), and is non-vacuous only because a real transition happened
  first: "nothing changed" proves something when there is something to change.
* ``test_create_404_precedes_body_validation`` is what catches the visibility
  check written as the handler's first statement rather than as a dependency.
* ``test_list_statement_count_does_not_grow_with_rows`` is what catches the
  lazy-loaded ``status`` / ``changed_by`` that no correctness assertion notices.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine

from app.api.routes import status_changes as status_changes_module
from app.db.models import ServiceRequest, Status, StatusHistory

REQUESTS = "/api/v1/service-requests"

# A fixed instant, so "oldest first" is a property of the data rather than of
# how fast the test ran. Postgres' `now()` is transaction-scoped, so rows seeded
# in one test would otherwise all share a `changed_at` by accident — which would
# make the ordering assertions pass without ordering by `changed_at` at all.
BASE_TIME = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)

# The four seeded rows, in `sort_order`. Spelled out rather than read from the
# table because the frontend's stepper depends on this exact vocabulary.
STATUS_NAMES = ("open", "in_progress", "resolved", "closed")


def changes_url(request_id: object) -> str:
    return f"{REQUESTS}/{request_id}/status-changes"


def request_body(**overrides: object) -> dict[str, object]:
    """A valid `POST /service-requests` body, for tests that need a real parent."""
    body: dict[str, object] = {
        "title": "VPN not connecting",
        "description": "Drops about five minutes after connecting.",
        "priority": "high",
    }
    body.update(overrides)
    return body


def assert_envelope(response, status_code: int, code: str) -> dict:
    """XC-4's shape, whole — not just the status line."""
    assert response.status_code == status_code, response.text
    body = response.json()
    assert "detail" not in body, "FastAPI's default shape leaked through"
    assert set(body) == {"error"}
    error = body["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]
    return error


@contextmanager
def statement_counter(engine: Engine):
    """Record every SQL statement executed on ``engine`` while inside."""
    statements: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", _record)


@contextmanager
def failing_statement(engine: Engine, fragment: str):
    """Make any statement containing ``fragment`` raise, mid-transaction.

    The counterpart to sabotaging a model: this fails a *specific* write without
    the route knowing, which is how the second of SC-5's two writes can be made
    to fail while the first has already been emitted. A monkeypatched model
    cannot do that — both writes here reference the same status id, so a bad one
    breaks whichever of them runs first.
    """

    def _maybe_fail(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if fragment in statement:
            raise RuntimeError(f"sabotaged statement: {fragment}")

    event.listen(engine, "before_cursor_execute", _maybe_fail)
    try:
        yield
    finally:
        event.remove(engine, "before_cursor_execute", _maybe_fail)


@pytest.fixture
def status_by_name(db_session):
    def _by_name(name: str) -> Status:
        return db_session.execute(
            select(Status).where(Status.name == name)
        ).scalar_one()

    return _by_name


@pytest.fixture
def make_status_change(db_session, open_status):
    """A `status_history` row factory. Everything rolls back, so no cleanup.

    Writes the row directly rather than through the endpoint, so a test can pin
    `changed_at` — the ordering assertions need distinct timestamps, and every
    row a single test transaction writes through the API shares one.
    """

    def _make(request, changed_by, **overrides: object) -> StatusHistory:
        fields: dict[str, object] = dict(
            service_request_id=request.id,
            status_id=open_status.id,
            changed_by_id=None if changed_by is None else changed_by.id,
        )
        fields.update(overrides)
        change = StatusHistory(**fields)
        db_session.add(change)
        db_session.flush()
        return change

    return _make


@pytest.fixture
def history_for(db_session):
    """Every `status_history` row for a request, read back from the database."""

    def _history(request_id: uuid.UUID) -> list[StatusHistory]:
        return list(
            db_session.execute(
                select(StatusHistory).where(
                    StatusHistory.service_request_id == request_id
                )
            )
            .scalars()
            .all()
        )

    return _history


# --- XC-5: both routes are gated ---------------------------------------------


@pytest.mark.parametrize(
    ("method", "kwargs"),
    [
        ("get", {}),
        # The CSRF header is sent so XC-9's 403 can't stand in for the 401 under
        # test — this asserts the auth gate, not the middleware in front of it.
        (
            "post",
            {
                "json": {"status_id": str(uuid.uuid4())},
                "headers": {"X-Requested-With": "x"},
            },
        ),
    ],
)
def test_requires_a_session(method, kwargs, make_user, make_service_request, client):
    """XC-5 for the status-change routes, asserted rather than assumed.

    backend/CLAUDE.md asks for this on every new protected route even though
    XC-5 was proven generically in T-AUTH-2: every other test in this file
    authenticates, so a route declared without its dependency would pass all of
    them. The list route is exactly the case where the omission would not break
    by side effect — nothing in its body reads the caller, so dropping the gate
    doesn't crash, it just hands a stranger someone else's history.
    """
    request = make_service_request(make_user())

    response = getattr(client, method)(changes_url(request.id), **kwargs)

    assert_envelope(response, 401, "UNAUTHENTICATED")


# --- GET: shape, order, paging (SC-1, XC-10, XC-11) --------------------------


def test_status_change_shape_matches_the_contract(
    make_user, make_service_request, make_status_change, client_for, status_by_name
):
    """design.md §5's `StatusChange`, field for field."""
    owner = make_user()
    admin = make_user(role="admin")
    request = make_service_request(owner)
    change = make_status_change(
        request,
        admin,
        status_id=status_by_name("in_progress").id,
        note="Escalated to network team.",
    )

    item = client_for(owner).get(changes_url(request.id)).json()["items"][0]

    assert set(item) == {"id", "status", "changed_by", "note", "changed_at"}
    assert item["id"] == str(change.id)
    # The embedded shared shapes, not restated copies (design.md §1).
    assert set(item["status"]) == {"id", "name", "sort_order", "is_terminal"}
    assert item["status"]["name"] == "in_progress"
    # design.md §0 decision 4: a structured user summary, never a pre-formatted
    # display string like the prototype's `'Priya Nair — IT Service Desk'`.
    assert set(item["changed_by"]) == {"id", "first_name", "last_name", "role"}
    assert item["changed_by"]["id"] == str(admin.id)
    assert item["note"] == "Escalated to network team."
    # XC-2: ISO 8601, UTC, explicit offset.
    assert item["changed_at"].endswith("Z")


def test_changed_by_is_null_for_an_actorless_transition(
    make_user, make_service_request, make_status_change, client_for
):
    """design.md §5 — `changed_by` is nullable, and the shape survives it.

    The column is ON DELETE SET NULL, so a transition whose actor's account was
    later deleted keeps its record and loses its author. Typed non-optional in
    the response schema, that row would serialise as a 500 — a 200 that is
    only reachable for as long as no user is ever deleted.
    """
    owner = make_user()
    request = make_service_request(owner)
    make_status_change(request, None)

    item = client_for(owner).get(changes_url(request.id)).json()["items"][0]

    assert item["changed_by"] is None


def test_list_envelope_shape(make_user, make_service_request, client_for):
    """XC-10 — the four envelope keys, with the documented defaults."""
    owner = make_user()
    request = make_service_request(owner)

    body = client_for(owner).get(changes_url(request.id)).json()

    assert set(body) == {"items", "total", "page", "page_size"}
    assert body["items"] == []
    assert body["total"] == 0
    assert body["page"] == 1
    assert body["page_size"] == 20


def test_oldest_first(
    make_user, make_service_request, make_status_change, client_for
):
    """SC-1 — `changed_at` ascending, the opposite of the request list's order.

    A timeline reads forwards; SR-15's list reads newest-first because it is an
    inbox. Asserted rather than assumed because the two endpoints sit in the
    same API and the wrong one is a plausible copy — and because the frontend's
    stepper walks this array in order.
    """
    owner = make_user()
    request = make_service_request(owner)
    oldest = make_status_change(request, owner, changed_at=BASE_TIME)
    middle = make_status_change(request, owner, changed_at=BASE_TIME.replace(hour=10))
    newest = make_status_change(request, owner, changed_at=BASE_TIME.replace(hour=11))

    items = client_for(owner).get(changes_url(request.id)).json()["items"]

    assert [item["id"] for item in items] == [
        str(oldest.id),
        str(middle.id),
        str(newest.id),
    ]


def test_identical_timestamps_order_by_id_and_stay_stable(
    make_user, make_service_request, make_status_change, client_for
):
    """SC-1 — `id` ascending breaks a `changed_at` tie, repeatably.

    Transitions sharing a timestamp are not hypothetical: `now()` is
    transaction-wide in Postgres. Without a tiebreaker the database may return
    equal-keyed rows in any order it likes, which under paging means a row can
    appear on two pages or on none.
    """
    owner = make_user()
    request = make_service_request(owner)
    expected = sorted(
        str(make_status_change(request, owner, changed_at=BASE_TIME).id)
        for _ in range(5)
    )

    client = client_for(owner)
    first = [i["id"] for i in client.get(changes_url(request.id)).json()["items"]]
    second = [i["id"] for i in client.get(changes_url(request.id)).json()["items"]]

    assert first == expected
    assert second == expected


def test_paging_walks_the_rows_without_overlap(
    make_user, make_service_request, make_status_change, client_for
):
    """XC-10 — `page` is 1-based and pages don't repeat rows."""
    owner = make_user()
    request = make_service_request(owner)
    for index in range(5):
        make_status_change(request, owner, changed_at=BASE_TIME.replace(minute=index))

    client = client_for(owner)
    first = client.get(changes_url(request.id), params={"page": 1, "page_size": 2})
    second = client.get(changes_url(request.id), params={"page": 2, "page_size": 2})

    assert first.json()["total"] == second.json()["total"] == 5
    assert len(first.json()["items"]) == len(second.json()["items"]) == 2
    assert {item["id"] for item in first.json()["items"]}.isdisjoint(
        item["id"] for item in second.json()["items"]
    )


def test_page_size_over_the_maximum_clamps(
    make_user, make_service_request, client_for
):
    """XC-11 — an over-large `page_size` clamps to 100; it does not 422."""
    owner = make_user()
    request = make_service_request(owner)

    body = (
        client_for(owner)
        .get(changes_url(request.id), params={"page_size": 250})
        .json()
    )

    assert body["page_size"] == 100


def test_list_is_scoped_to_its_parent_request(
    make_user, make_service_request, make_status_change, client_for
):
    """SC-1 — a sub-resource returns its own parent's rows and no others."""
    owner = make_user()
    mine = make_service_request(owner)
    other = make_service_request(owner)
    on_mine = make_status_change(mine, owner)
    on_other = make_status_change(other, owner)

    body = client_for(owner).get(changes_url(mine.id)).json()

    assert [item["id"] for item in body["items"]] == [str(on_mine.id)]
    assert str(on_other.id) not in body["items"][0]["id"]
    assert body["total"] == 1


# --- SC-3: only rows that actually exist -------------------------------------


def test_history_holds_only_real_transitions(
    make_user, client_for, status_by_name, history_for
):
    """SC-3 — the count is the number of transitions made, never a fixed number.

    The locked decision (design.md §0) is that the API never synthesises a
    placeholder row for a status not yet reached: the stepper's hollow steps are
    the frontend's diff against `GET /statuses`, not rows from here. So the
    assertion is that the payload tracks what happened — one row for a
    brand-new request (SR-14's `open`), one more per transition — and that the
    two statuses never reached are absent entirely.

    Asserted against a request created through the API rather than through the
    fixture, because SR-14's opening row is written by the create endpoint: a
    fixture-made request has an empty history and would put the baseline at
    zero, which is exactly the number this test needs to be wrong about.
    """
    admin = make_user(role="admin")
    client = client_for(admin)
    request_id = uuid.UUID(client.post(REQUESTS, json=request_body()).json()["id"])

    baseline = client.get(changes_url(request_id)).json()
    assert baseline["total"] == 1
    assert [item["status"]["name"] for item in baseline["items"]] == ["open"]

    for name in ("in_progress", "resolved"):
        response = client.post(
            changes_url(request_id),
            json={"status_id": str(status_by_name(name).id)},
        )
        assert response.status_code == 201, response.text

    listed = client.get(changes_url(request_id))
    body = listed.json()

    assert body["total"] == 3
    assert len(body["items"]) == 3
    # The database's own count, as the independent check on `total`.
    assert len(history_for(request_id)) == 3
    returned = {item["status"]["name"] for item in body["items"]}
    assert returned == {"open", "in_progress", "resolved"}
    # The two never reached are absent from the list response entirely — not
    # present with a null timestamp, which is the shape design.md §0 ruled out.
    assert "closed" not in listed.text
    assert all(item["changed_at"] for item in body["items"])


# --- SC-2: parent visibility -------------------------------------------------


def test_list_404s_for_a_parent_the_caller_cannot_see(
    make_user, make_service_request, make_status_change, client_for
):
    """SC-2 / XC-7 — three different causes, one identical answer.

    Someone else's request, a well-formed id that matches nothing, and a string
    that is not an id at all must not be tellable apart, and must match SR-12's
    answer on the parent route itself. A 403 on the first would confirm the
    request exists; a 422 on the third would confirm the other two are at least
    *shaped* like real ids.
    """
    caller = make_user()
    someone_elses = make_service_request(make_user())
    make_status_change(someone_elses, caller)
    client = client_for(caller)

    responses = [
        client.get(changes_url(someone_elses.id)),
        client.get(changes_url(uuid.uuid4())),
        client.get(changes_url("not-a-uuid")),
        # The parent route's own 404, which these must be identical to — the
        # point of SC-2 citing SR-12 rather than restating it.
        client.get(f"{REQUESTS}/{someone_elses.id}"),
    ]

    for response in responses:
        assert_envelope(response, 404, "NOT_FOUND")
    assert len({response.content for response in responses}) == 1


def test_admin_can_read_any_requests_history(
    make_user, make_service_request, make_status_change, client_for
):
    """SC-2 inherits SR-11: an admin's visibility is not limited to their own."""
    admin = make_user(role="admin")
    request = make_service_request(make_user())
    change = make_status_change(request, make_user())

    body = client_for(admin).get(changes_url(request.id)).json()

    assert [item["id"] for item in body["items"]] == [str(change.id)]


# --- SC-4: only an admin may transition --------------------------------------


def test_user_posting_a_status_change_is_refused(
    make_user, make_service_request, client_for, status_by_name, history_for
):
    """SC-4 / XC-6 — 403 on a request the caller can see, and no row behind it.

    The parent here is the caller's *own* request, which is what isolates SC-4
    from SC-8: the caller passes the visibility check and is refused on role
    alone. The "no row, no move" half is the one worth having — a handler that
    checked the role after writing would answer 403 and still have transitioned
    the request.
    """
    owner = make_user()
    request = make_service_request(owner)
    before = request.current_status_id

    response = client_for(owner).post(
        changes_url(request.id),
        json={"status_id": str(status_by_name("closed").id)},
    )

    error = assert_envelope(response, 403, "FORBIDDEN")
    # design.md §1 reserves `fields` for VALIDATION_ERROR: this is a permission
    # the caller lacks, not a field they typed wrongly.
    assert "fields" not in error

    db_rows = history_for(request.id)
    assert db_rows == []
    assert request.current_status_id == before


def test_user_posting_to_an_invisible_parent_gets_the_visibility_answer(
    make_user, make_service_request, client_for, status_by_name
):
    """SC-4 and SC-8 overlap here, and the module picks SC-8 — pinned.

    A `user`-role caller with no visibility into the parent satisfies both
    requirements' conditions, and only one response can be sent. The route
    declares `get_visible_parent_request` ahead of the role gate so this answers
    404: SC-8 names the case specifically, and a 403 would tell a caller who
    cannot see the request that it exists — the disclosure XC-7 exists to
    prevent. Byte-identical to the read path's 404 for the same reason.

    This is a dependency *ordering*, which nothing else would catch: swap the
    two parameters and every other test in this file still passes.
    """
    caller = make_user()
    someone_elses = make_service_request(make_user())
    client = client_for(caller)
    body = {"status_id": str(status_by_name("closed").id)}

    responses = [
        client.post(changes_url(someone_elses.id), json=body),
        client.post(changes_url(uuid.uuid4()), json=body),
        client.get(changes_url(someone_elses.id)),
    ]

    for response in responses:
        assert_envelope(response, 404, "NOT_FOUND")
    assert len({response.content for response in responses}) == 1


# --- SC-5: the transition, and its atomicity ---------------------------------


def test_admin_transition_returns_the_created_change(
    make_user, make_service_request, client_for, status_by_name, history_for
):
    """SC-5 — a 201 carrying the created row, attributed to the admin."""
    admin = make_user(role="admin")
    request = make_service_request(make_user())
    in_progress = status_by_name("in_progress")

    response = client_for(admin).post(
        changes_url(request.id),
        json={"status_id": str(in_progress.id), "note": "Escalated."},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"]["id"] == str(in_progress.id)
    assert body["status"]["name"] == "in_progress"
    assert body["changed_by"]["id"] == str(admin.id)
    assert body["note"] == "Escalated."

    # Read back through the database rather than trusting the response to
    # describe what was stored.
    rows = history_for(request.id)
    assert len(rows) == 1
    assert str(rows[0].id) == body["id"]
    assert rows[0].status_id == in_progress.id
    assert rows[0].changed_by_id == admin.id


def test_transition_updates_the_parents_current_status(
    make_user, make_service_request, client_for, status_by_name, db_session
):
    """SC-5's second write — the parent moves, and says so on its own endpoint."""
    admin = make_user(role="admin")
    request = make_service_request(make_user())
    resolved = status_by_name("resolved")
    client = client_for(admin)

    client.post(changes_url(request.id), json={"status_id": str(resolved.id)})

    db_session.expire_all()
    assert db_session.get(ServiceRequest, request.id).current_status_id == resolved.id
    detail = client.get(f"{REQUESTS}/{request.id}").json()
    assert detail["status"]["name"] == "resolved"


def test_created_change_appears_in_the_list(
    make_user, make_service_request, client_for, status_by_name
):
    """SC-5 + SC-1 — the write is visible to the read, same shape either way."""
    admin = make_user(role="admin")
    request = make_service_request(make_user())
    client = client_for(admin)

    created = client.post(
        changes_url(request.id),
        json={"status_id": str(status_by_name("closed").id)},
    ).json()
    listed = client.get(changes_url(request.id)).json()["items"]

    assert listed == [created]


def test_transition_writes_nothing_when_the_history_insert_fails(
    monkeypatch, make_user, client_for, db_session, status_by_name, history_for
):
    """SC-5 — atomicity, proven by observing the failure.

    A green success path shows the two writes arriving together; it cannot show
    that they *must*. Only forcing one to fail and finding the other absent does
    that — backend/CLAUDE.md's "verify it can fail" rule applied to a
    transaction boundary rather than to a constraint. Splitting the handler into
    two commits passes every other test in this file.

    The parent is created **through the API**, not through the fixture, and that
    is load-bearing. A fixture row lives inside the test's SAVEPOINT, which the
    failed request rolls back along with everything else — so the assertion
    below would query a row that no longer exists and pass vacuously, proving
    only that a deleted request has no history. Creating it through the endpoint
    commits it into the outer transaction, where it survives to be checked.
    """
    admin = make_user(role="admin")
    client = client_for(admin)
    open_status_id = status_by_name("open").id
    target_status_id = status_by_name("in_progress").id
    # Committed by the endpoint, so it outlives the rollback under test. SR-14
    # gives it exactly one history row, which is the count that must not change.
    request_id = uuid.UUID(client.post(REQUESTS, json=request_body()).json()["id"])

    def _sabotaged_history(**kwargs: object) -> StatusHistory:
        # A status_id matching no `statuses` row: the INSERT fails on its
        # foreign key at flush time — mid-transaction, the way a real failure
        # would, rather than before any SQL has been emitted.
        return StatusHistory(**{**kwargs, "status_id": uuid.uuid4()})

    monkeypatch.setattr(status_changes_module, "StatusHistory", _sabotaged_history)

    response = client_for(admin, raise_server_exceptions=False).post(
        changes_url(request_id), json={"status_id": str(target_status_id)}
    )

    assert_envelope(response, 500, "INTERNAL_ERROR")

    db_session.rollback()
    parent = db_session.get(ServiceRequest, request_id)
    assert parent is not None, (
        "the committed request vanished with the rollback — the assertions "
        "below would have passed without proving anything"
    )
    assert parent.current_status_id == open_status_id, (
        "the parent moved despite the history insert failing — the two writes "
        "are not in one transaction"
    )
    assert len(history_for(request_id)) == 1


def test_transition_writes_nothing_when_the_parent_update_fails(
    engine, make_user, client_for, db_session, status_by_name, history_for
):
    """SC-5 — the same atomicity, with the *other* write failing.

    The test above sabotages the history insert, which catches a handler that
    moved the parent first and committed. It cannot catch the mirror image — a
    handler that commits the history row and only then updates the parent —
    because the insert it breaks is that implementation's first write too.

    Failing the `UPDATE service_requests` specifically is what closes that half:
    whichever order the handler chooses, the history row must not survive a
    failure of the parent's update. Sabotaging the model cannot express this,
    since both writes reference the same status id.
    """
    admin = make_user(role="admin")
    client = client_for(admin)
    open_status_id = status_by_name("open").id
    target_status_id = status_by_name("in_progress").id
    # Committed by the endpoint, so it outlives the rollback under test, with
    # SR-14's single history row as the count that must not change.
    request_id = uuid.UUID(client.post(REQUESTS, json=request_body()).json()["id"])

    with failing_statement(engine, "UPDATE service_requests"):
        response = client_for(admin, raise_server_exceptions=False).post(
            changes_url(request_id), json={"status_id": str(target_status_id)}
        )

    assert_envelope(response, 500, "INTERNAL_ERROR")

    db_session.rollback()
    parent = db_session.get(ServiceRequest, request_id)
    assert parent is not None, (
        "the committed request vanished with the rollback — the assertions "
        "below would have passed without proving anything"
    )
    assert parent.current_status_id == open_status_id
    assert len(history_for(request_id)) == 1, (
        "the history row survived a failed parent update — the two writes are "
        "not in one transaction"
    )


# --- SC-6: an unusable status_id changes nothing -----------------------------


@pytest.mark.parametrize(
    "body",
    [{}, {"status_id": None}, {"status_id": "not-a-uuid"}, {"note": "no status"}],
    ids=["missing", "null", "malformed", "note-only"],
)
def test_create_rejects_a_malformed_status_id(
    body, make_user, make_service_request, client_for
):
    """SC-6 — 422 with `fields.status_id` populated, not a bare status code."""
    admin = make_user(role="admin")
    request = make_service_request(make_user())

    response = client_for(admin).post(changes_url(request.id), json=body)

    error = assert_envelope(response, 422, "VALIDATION_ERROR")
    assert set(error["fields"]) == {"status_id"}, error["fields"]


def test_create_rejects_a_status_id_matching_no_row(
    make_user, make_service_request, client_for
):
    """SC-6 — a well-formed id for a status that doesn't exist is still a 422.

    This is the half Pydantic cannot answer: the valid set is the `statuses`
    table, so the route checks it and raises the same envelope by hand rather
    than letting an unknown id reach the INSERT and surface as a foreign-key
    500.
    """
    admin = make_user(role="admin")
    request = make_service_request(make_user())

    response = client_for(admin).post(
        changes_url(request.id), json={"status_id": str(uuid.uuid4())}
    )

    error = assert_envelope(response, 422, "VALIDATION_ERROR")
    assert set(error["fields"]) == {"status_id"}, error["fields"]


def test_rejected_status_id_applies_nothing(
    make_user, client_for, status_by_name, history_for, db_session
):
    """SC-6's second half — "SHALL NOT partially apply", after a real change.

    Asserting "nothing moved" against a request that had never moved would pass
    against any implementation at all, including one that writes half a
    transition. So a valid transition is made first: the state the rejected call
    must leave untouched is a state something actually put there.
    """
    admin = make_user(role="admin")
    client = client_for(admin)
    request_id = uuid.UUID(client.post(REQUESTS, json=request_body()).json()["id"])
    in_progress_id = status_by_name("in_progress").id
    assert (
        client.post(
            changes_url(request_id), json={"status_id": str(in_progress_id)}
        ).status_code
        == 201
    )

    response = client.post(
        changes_url(request_id),
        json={"status_id": str(uuid.uuid4()), "note": "should not be stored"},
    )

    assert_envelope(response, 422, "VALIDATION_ERROR")
    db_session.expire_all()
    # Still the two rows SR-14 and the accepted transition left, and still
    # pointing where the accepted transition put it.
    assert len(history_for(request_id)) == 2
    assert db_session.get(ServiceRequest, request_id).current_status_id == in_progress_id


# --- SC-8: visibility precedes everything ------------------------------------


def test_create_404s_for_a_parent_that_does_not_exist(
    make_user, client_for, status_by_name
):
    """SC-8 — the same indistinguishable answers as the read path, for an admin.

    An admin can see every request that exists, so their 404 is purely about
    existence — which makes this the clean test of SC-8 without SC-4's role rule
    in the way.
    """
    admin = make_user(role="admin")
    client = client_for(admin)
    body = {"status_id": str(status_by_name("closed").id)}

    responses = [
        client.post(changes_url(uuid.uuid4()), json=body),
        client.post(changes_url("not-a-uuid"), json=body),
        client.get(changes_url(uuid.uuid4())),
    ]

    for response in responses:
        assert_envelope(response, 404, "NOT_FOUND")
    assert len({response.content for response in responses}) == 1


@pytest.mark.parametrize(
    "body",
    [{}, {"status_id": "not-a-uuid"}, {"status_id": str(uuid.uuid4())}],
    ids=["missing-status", "malformed-status", "unknown-status"],
)
def test_create_404_precedes_body_validation(body, make_user, client_for):
    """SC-8 — "before evaluating `status_id`", asserted literally.

    This is the test that pins the visibility check to a *dependency*. FastAPI
    resolves dependencies before it validates a request body, so the check has
    to live there: written as the handler's first statement it would run after
    Pydantic had already answered 422, and a caller who cannot see the request
    would learn it exists from the fact that the API critiqued their body
    instead of denying the resource. T-CM-0 found this the hard way on the
    comment route, which has the identical shape.
    """
    admin = make_user(role="admin")

    response = client_for(admin).post(changes_url(uuid.uuid4()), json=body)

    assert_envelope(response, 404, "NOT_FOUND")


# --- SC-7: the note ----------------------------------------------------------


@pytest.mark.parametrize(
    ("sent", "stored"),
    [
        ({"note": "Escalated to network team."}, "Escalated to network team."),
        ({"note": None}, None),
        ({}, None),
        # No enforced maximum (SC-7) — the column is unbounded TEXT, so unlike a
        # comment's 5000-character ceiling there is nothing here to reject.
        ({"note": "n" * 20000}, "n" * 20000),
        # Stored verbatim: no trimming, no collapsing of an empty note into null.
        ({"note": "  spaced  "}, "  spaced  "),
    ],
    ids=["text", "explicit-null", "omitted", "very-long", "verbatim"],
)
def test_note_is_optional_and_stored_verbatim(
    sent, stored, make_user, make_service_request, client_for, status_by_name, history_for
):
    """SC-7 — optional, unbounded, unaltered."""
    admin = make_user(role="admin")
    request = make_service_request(make_user())

    response = client_for(admin).post(
        changes_url(request.id),
        json={"status_id": str(status_by_name("closed").id), **sent},
    )

    assert response.status_code == 201, response.text
    assert response.json()["note"] == stored
    assert history_for(request.id)[0].note == stored


# --- SR-14's invariant, after a transition -----------------------------------


def test_current_status_matches_the_latest_transition_throughout(
    make_user, client_for, status_by_name, history_for, db_session
):
    """SR-14's invariant holds after every transition, not only at creation.

    Checked after each step rather than once at the end, because a handler that
    wrote history correctly and updated `current_status_id` to the wrong row
    would still finish in the right place if the last write happened to be
    right.

    "Most recent" is pinned to the order the transitions were *posted* rather
    than read off `changed_at`: Postgres' `now()` is transaction-scoped and the
    whole test runs in one transaction, so every row here shares a timestamp to
    the microsecond. That is a property of the harness, not of production — and
    comparing against the posting order is the stronger assertion anyway.
    """
    admin = make_user(role="admin")
    client = client_for(admin)
    request_id = uuid.UUID(client.post(REQUESTS, json=request_body()).json()["id"])

    db_session.expire_all()
    assert (
        db_session.get(ServiceRequest, request_id).current_status_id
        == status_by_name("open").id
    ), "SR-14's own half: a new request already points at `open`"

    for step, name in enumerate(STATUS_NAMES[1:], start=2):
        target = status_by_name(name)
        response = client.post(
            changes_url(request_id), json={"status_id": str(target.id)}
        )
        assert response.status_code == 201, response.text

        db_session.expire_all()
        parent = db_session.get(ServiceRequest, request_id)
        assert parent.current_status_id == target.id
        rows = history_for(request_id)
        assert len(rows) == step
        # The row just written is the one the parent points at.
        assert {row.id for row in rows if row.status_id == target.id} == {
            uuid.UUID(response.json()["id"])
        }


# --- XC-8: server-controlled fields ------------------------------------------


def test_create_ignores_client_supplied_server_fields(
    make_user, make_service_request, client_for, status_by_name, history_for
):
    """XC-8 — `changed_by_id`, `service_request_id` and `changed_at` are ours.

    The requirement is specifically *ignore*, not *reject*: a 422 here would
    also stop the values being applied and would still be a contract break,
    because XC-8 says a field documented as "not accepted" must not change what
    happens.
    """
    admin = make_user(role="admin")
    impostor = make_user()
    request = make_service_request(make_user())
    other_request = make_service_request(make_user())

    response = client_for(admin).post(
        changes_url(request.id),
        json={
            "status_id": str(status_by_name("closed").id),
            "changed_by_id": str(impostor.id),
            "service_request_id": str(other_request.id),
            "changed_at": "2000-01-01T00:00:00Z",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["changed_by"]["id"] == str(admin.id)
    assert not response.json()["changed_at"].startswith("2000")
    rows = history_for(request.id)
    assert len(rows) == 1
    assert rows[0].changed_by_id == admin.id
    assert history_for(other_request.id) == []


# --- AUTH-5 / XC-15 ----------------------------------------------------------


def test_no_response_carries_a_password_field(
    make_user, make_service_request, make_status_change, client_for, status_by_name
):
    """AUTH-5 / XC-15 — including on the error paths, not only on 2xx.

    Every user in these payloads serialises through `UserSummary`, which has no
    such field to expose. The error responses are in the list on purpose: they
    are the paths a success-path test never covers and the ones where a handler
    rendering an exception's own text would leak the row it was excluding.
    """
    admin = make_user(role="admin")
    request = make_service_request(make_user())
    make_status_change(request, admin)
    client = client_for(admin)
    valid = {"status_id": str(status_by_name("closed").id)}

    for response in (
        client.get(changes_url(request.id)),
        client.post(changes_url(request.id), json=valid),
        client.get(changes_url("not-a-uuid")),
        client.post(changes_url(request.id), json={}),
        client.post(changes_url(request.id), json={"status_id": str(uuid.uuid4())}),
        client.post(changes_url(uuid.uuid4()), json=valid),
    ):
        assert "password" not in response.text.lower(), response.text


# --- N+1 ---------------------------------------------------------------------


def test_list_statement_count_does_not_grow_with_rows(
    engine,
    db_session,
    make_user,
    make_service_request,
    make_status_change,
    client_for,
    status_by_name,
):
    """The two eager loads, asserted as a property rather than as a number.

    Lazy-loading `status` and `changed_by` costs 1 + 2n statements for a page of
    n, and every correctness test in this file passes either way — the payload
    is identical, just assembled far more expensively. Comparing two row counts
    is what makes the growth visible; a "fewer than N" bound would be satisfied
    by an N+1 on a small enough page.

    Two things in the obvious version of this test make it pass with the
    joinedloads removed, and both are designed out here per T-SR-0's finding:

    * The rows are seeded through the very session the request handler then
      uses, so every related row is already in SQLAlchemy's identity map and a
      lazy many-to-one load is answered from memory without touching the
      database. `expunge_all()` empties it, which is not a trick to force a
      failure — it restores the production condition, where `get_db` yields a
      fresh session per request and the identity map is always cold.
    * Homogeneous rows make an N+1 self-limit: every transition sharing one
      actor would cost one query no matter how many rows there are. So each row
      gets its own `changed_by`, and the statuses cycle — the `statuses` table
      holds only four rows, so it is `changed_by` that grows without bound and
      `status` that grows from three distinct values to four. Either is enough
      to break the equality below.
    """
    admin = make_user(role="admin")
    request = make_service_request(make_user())
    # Built before the first `expunge_all` — it reads `admin.id` and
    # `admin.role` to mint the token, which a detached instance would not answer
    # for. The parent's id and the status ids are read for the same reason.
    client = client_for(admin)
    parent_url = changes_url(request.id)
    status_ids = [status_by_name(name).id for name in STATUS_NAMES]

    def seed(count: int, start: int) -> None:
        for index in range(start, start + count):
            make_status_change(
                request,
                make_user(),
                status_id=status_ids[index % len(status_ids)],
                changed_at=BASE_TIME.replace(minute=index % 60),
            )

    def statements_for(expected_rows: int) -> int:
        db_session.expunge_all()
        with statement_counter(engine) as statements:
            body = client.get(parent_url, params={"page_size": 100}).json()
            assert len(body["items"]) == expected_rows, body["total"]
            return len(statements)

    seed(3, start=0)
    few_rows = statements_for(3)

    seed(12, start=3)
    many_rows = statements_for(15)

    assert few_rows == many_rows, (
        f"{few_rows} statements for 3 transitions, {many_rows} for 15 — the "
        "per-row queries are the lazy loads the joinedloads exist to prevent"
    )
