"""The three service-request endpoints (T-SR-0; SR-1 .. SR-15, XC-7 .. XC-11).

Contract tests against the real Postgres test database and the real
``create_app()`` (backend/CLAUDE.md) — no SQLite, no hand-assembled app.

Error assertions check the whole envelope, not the status code alone: a 422
carrying the wrong ``fields`` key is still a broken contract even though the
number is right.

Two of these tests are written to fail for a specific reason rather than to
describe a feature, and are worth reading as such:
``test_total_counts_only_visible_rows`` is what catches ownership scoping
applied in Python instead of in SQL, and
``test_list_statement_count_does_not_grow_with_rows`` is what catches the
lazy-loaded N+1 that no correctness assertion would ever notice.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import event, select
from sqlalchemy.engine import Engine

from app.api.routes import service_requests as service_requests_module
from app.db.models import ServiceRequest, Status, StatusHistory

LIST = "/api/v1/service-requests"

# A fixed instant, so "newest first" is a property of the data rather than of
# how fast the test ran. Postgres' `now()` is transaction-scoped, so rows
# seeded in one test would otherwise all share a created_at by accident — which
# would make the ordering assertions pass without ordering by created_at at all.
BASE_TIME = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)


def detail(request_id: object) -> str:
    return f"{LIST}/{request_id}"


def create_body(**overrides: object) -> dict[str, object]:
    """A valid `POST /service-requests` body (design.md §4)."""
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


def assert_no_password(response) -> None:
    """AUTH-5 / XC-15, checked against the raw bytes rather than parsed keys.

    A nested object or an exception message that happened to quote a row would
    not show up in a key-by-key comparison, and those are exactly the paths
    that leak.
    """
    assert "password" not in response.text.lower(), response.text


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


@pytest.fixture
def status_by_name(db_session):
    def _by_name(name: str) -> Status:
        return db_session.execute(
            select(Status).where(Status.name == name)
        ).scalar_one()

    return _by_name


# --- XC-5: every one of these routes is gated ---------------------------------


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("get", LIST, {}),
        # The CSRF header is sent so XC-9's 403 can't stand in for the 401 under
        # test — this asserts the auth gate, not the middleware in front of it.
        ("post", LIST, {"json": create_body(), "headers": {"X-Requested-With": "x"}}),
        ("get", f"{LIST}/{uuid.uuid4()}", {}),
    ],
)
def test_requires_a_session(method, path, kwargs, client):
    """XC-5 — asserted per route, not inherited from T-AUTH-2's generic proof.

    A route declared without its auth dependency still passes every test in
    this file, because every other test authenticates. Here that omission would
    surface only by side effect — these handlers happen to need `user` for
    scoping — and "happens to break" is not a gate. `GET /statuses` is the one
    route deliberately outside this rule (ST-1); see `test_statuses.py`.
    """
    response = getattr(client, method)(path, **kwargs)

    assert_envelope(response, 401, "UNAUTHENTICATED")


# --- GET /service-requests: ownership scoping (SR-1, SR-2) -------------------


def test_user_sees_only_their_own_requests(
    make_user, make_service_request, client_for
):
    """SR-1 — a `user`-role caller's list is scoped to their own rows."""
    owner = make_user()
    other = make_user()
    mine = {str(make_service_request(owner).id) for _ in range(2)}
    theirs = {str(make_service_request(other).id) for _ in range(3)}

    body = client_for(owner).get(LIST).json()
    returned = {item["id"] for item in body["items"]}

    # Both halves asserted on specific ids, and both non-empty: a test where
    # each user happened to own zero requests would pass while proving nothing.
    assert mine and theirs
    assert returned == mine
    assert returned.isdisjoint(theirs)


def test_admin_sees_every_requestor(make_user, make_service_request, client_for):
    """SR-2 — an `admin`-role caller's list spans all requestors."""
    admin = make_user(role="admin")
    one = make_user()
    two = make_user()
    everyone = {str(make_service_request(one).id) for _ in range(2)} | {
        str(make_service_request(two).id) for _ in range(3)
    }

    body = client_for(admin).get(LIST).json()

    assert {item["id"] for item in body["items"]} == everyone
    assert body["total"] == 5


def test_total_counts_only_visible_rows(
    make_user, make_service_request, client_for
):
    """SR-1 + XC-10 — `total` is the scoped count, not the table count.

    This is the assertion that catches ownership applied *after* the fetch: a
    Python-side filter still returns the right items on page one, and reports a
    `total` that counts rows the caller will never be shown. The paginator then
    promises pages that come back empty.
    """
    owner = make_user()
    other = make_user()
    for _ in range(2):
        make_service_request(owner)
    for _ in range(3):
        make_service_request(other)

    body = client_for(owner).get(LIST).json()

    assert body["total"] == 2, "total counted rows outside the caller's scope"
    assert len(body["items"]) == 2


# --- GET /service-requests: filters (SR-3, SR-4) -----------------------------


def test_status_filter_narrows_to_that_status(
    make_user, make_service_request, client_for, status_by_name
):
    """SR-3 — a seeded status name filters on `current_status_id`."""
    owner = make_user()
    resolved = status_by_name("resolved")
    open_one = make_service_request(owner)
    resolved_one = make_service_request(owner, current_status_id=resolved.id)

    body = client_for(owner).get(LIST, params={"status": "resolved"}).json()

    returned = [item["id"] for item in body["items"]]
    assert returned == [str(resolved_one.id)]
    assert str(open_one.id) not in returned
    assert body["total"] == 1
    assert body["items"][0]["status"]["name"] == "resolved"


def test_unknown_status_is_422_not_an_empty_list(
    make_user, make_service_request, client_for
):
    """SR-3 — an unseeded status name is a validation failure, not "no matches".

    An empty 200 would tell a caller their filter worked and nothing matched,
    which is a different fact from "there is no such status" and points them at
    the wrong fix.
    """
    owner = make_user()
    make_service_request(owner)

    response = client_for(owner).get(LIST, params={"status": "in_limbo"})

    error = assert_envelope(response, 422, "VALIDATION_ERROR")
    assert set(error["fields"]) == {"status"}
    assert error["fields"]["status"]


def test_total_respects_filters_as_well_as_scope(
    make_user, make_service_request, client_for, status_by_name
):
    """T-DEBT-4 — `total` carries *every* predicate the page does.

    `test_total_counts_only_visible_rows` proves the count is scoped. This is
    the neighbouring bug, one predicate over: a `COUNT` that applies the
    ownership scope but not the `status` / `priority` filters. Every item-level
    assertion in this file still passes when that happens — the page holds
    exactly the right rows — and only `total` is wrong, so the paginator offers
    pages that come back empty.

    Scope and filter are exercised together rather than separately because the
    bug lives in the gap between them: rows exist here that the filter excludes
    *and* rows that the scope excludes, so a count missing either predicate
    reports a different, wrong number.
    """
    owner = make_user()
    other = make_user()
    resolved = status_by_name("resolved")

    make_service_request(owner, current_status_id=resolved.id, priority="high")
    make_service_request(owner, priority="high")  # open, so the filter drops it
    make_service_request(owner, current_status_id=resolved.id, priority="low")
    for _ in range(3):
        make_service_request(other, current_status_id=resolved.id, priority="high")

    body = (
        client_for(owner)
        .get(LIST, params={"status": "resolved", "priority": "high"})
        .json()
    )

    assert len(body["items"]) == 1
    assert body["total"] == 1, "total ignored the status/priority filters"


@pytest.mark.parametrize("priority", ["low", "medium", "high"])
def test_priority_filter_narrows_to_that_priority(
    priority, make_user, make_service_request, client_for
):
    """SR-4 — each accepted value filters, and only its own rows come back."""
    owner = make_user()
    by_priority = {
        value: make_service_request(owner, priority=value)
        for value in ("low", "medium", "high")
    }

    body = client_for(owner).get(LIST, params={"priority": priority}).json()

    assert [item["id"] for item in body["items"]] == [str(by_priority[priority].id)]
    assert body["total"] == 1


def test_unknown_priority_is_422(make_user, client_for):
    """SR-4 — outside {low, medium, high} is rejected by the schema layer."""
    response = client_for(make_user()).get(LIST, params={"priority": "urgent"})

    error = assert_envelope(response, 422, "VALIDATION_ERROR")
    assert set(error["fields"]) == {"priority"}


# --- GET /service-requests: shape, ordering, paging --------------------------


def test_every_list_item_carries_description(
    make_user, make_service_request, client_for
):
    """SR-5 — one shape for list and detail (design.md §0 decision 2)."""
    owner = make_user()
    request = make_service_request(owner, description="Full text, not a summary.")

    body = client_for(owner).get(LIST).json()

    assert body["items"][0]["description"] == "Full text, not a summary."
    assert body["items"][0]["id"] == str(request.id)


def test_list_item_shape_matches_the_contract(
    make_user, make_service_request, client_for
):
    """design.md §4's `ServiceRequest`, field for field."""
    owner = make_user()
    make_service_request(owner)

    item = client_for(owner).get(LIST).json()["items"][0]

    assert set(item) == {
        "id",
        "title",
        "request_type",
        "priority",
        "status",
        "requestor",
        "assignee",
        "created_at",
        "updated_at",
        "description",
    }
    assert set(item["status"]) == {"id", "name", "sort_order", "is_terminal"}
    assert set(item["requestor"]) == {"id", "first_name", "last_name", "role"}
    assert item["requestor"]["id"] == str(owner.id)
    # No assignment path exists in this phase (design.md §7).
    assert item["assignee"] is None
    # XC-2: ISO 8601, UTC, explicit offset.
    assert item["created_at"].endswith("Z")
    assert item["updated_at"].endswith("Z")


def test_list_envelope_shape(make_user, client_for):
    """XC-10 — the four envelope keys, with the documented defaults."""
    body = client_for(make_user()).get(LIST).json()

    assert set(body) == {"items", "total", "page", "page_size"}
    assert body["page"] == 1
    assert body["page_size"] == 20


def test_newest_first(make_user, make_service_request, client_for):
    """SR-15 — `created_at` descending."""
    owner = make_user()
    oldest = make_service_request(owner, created_at=BASE_TIME)
    middle = make_service_request(
        owner, created_at=BASE_TIME.replace(hour=10)
    )
    newest = make_service_request(owner, created_at=BASE_TIME.replace(hour=11))

    items = client_for(owner).get(LIST).json()["items"]

    assert [item["id"] for item in items] == [
        str(newest.id),
        str(middle.id),
        str(oldest.id),
    ]


def test_identical_timestamps_order_by_id_and_stay_stable(
    make_user, make_service_request, client_for
):
    """SR-15 — `id` descending breaks a `created_at` tie, repeatably.

    Rows sharing a timestamp are not hypothetical: `now()` is transaction-wide
    in Postgres, so anything created in one request shares an instant. Without
    a tiebreaker the database may return equal-keyed rows in any order it
    likes, which under paging means a row can appear on two pages or on none.
    """
    owner = make_user()
    ids = sorted(
        str(make_service_request(owner, created_at=BASE_TIME).id) for _ in range(5)
    )
    expected = sorted(ids, reverse=True)

    client = client_for(owner)
    first = [item["id"] for item in client.get(LIST).json()["items"]]
    second = [item["id"] for item in client.get(LIST).json()["items"]]

    assert first == expected
    assert second == expected


def test_page_size_over_the_maximum_clamps(
    make_user, make_service_request, client_for
):
    """XC-11 — an over-large `page_size` clamps to 100; it does not 422."""
    owner = make_user()
    make_service_request(owner)

    body = client_for(owner).get(LIST, params={"page_size": 250}).json()

    assert body["page_size"] == 100
    assert len(body["items"]) <= 100


def test_paging_walks_the_rows_without_overlap(
    make_user, make_service_request, client_for
):
    """XC-10 — `page` is 1-based and pages don't repeat rows."""
    owner = make_user()
    for index in range(5):
        make_service_request(owner, created_at=BASE_TIME.replace(minute=index))

    client = client_for(owner)
    first = client.get(LIST, params={"page": 1, "page_size": 2}).json()
    second = client.get(LIST, params={"page": 2, "page_size": 2}).json()

    assert first["total"] == second["total"] == 5
    assert len(first["items"]) == len(second["items"]) == 2
    assert {item["id"] for item in first["items"]}.isdisjoint(
        item["id"] for item in second["items"]
    )


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 0}])
def test_non_positive_paging_values_are_422(params, make_user, client_for):
    """XC-10/XC-11 — the floor is a validation rule; only the ceiling clamps."""
    response = client_for(make_user()).get(LIST, params=params)

    error = assert_envelope(response, 422, "VALIDATION_ERROR")
    assert set(error["fields"]) == set(params)


# --- POST /service-requests: validation (SR-6 .. SR-9) -----------------------


def test_create_returns_the_full_request(
    make_user, client_for, db_session, status_by_name
):
    """SR-6 — a 201 carrying the created row, with the server's own fields."""
    owner = make_user()

    response = client_for(owner).post(LIST, json=create_body())

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "VPN not connecting"
    assert body["priority"] == "high"
    assert body["request_type"] == "general"
    assert body["status"]["name"] == "open"
    assert body["requestor"]["id"] == str(owner.id)
    assert body["assignee"] is None

    row = db_session.get(ServiceRequest, uuid.UUID(body["id"]))
    assert row is not None
    assert row.requestor_id == owner.id
    assert row.current_status_id == status_by_name("open").id


@pytest.mark.parametrize(
    ("field", "value"),
    [
        # Exactly at each documented boundary, and one character past it.
        ("title", "t" * 200),
        ("description", "d" * 10000),
    ],
)
def test_create_accepts_the_boundary_length(field, value, make_user, client_for):
    """SR-7 / SR-8 — the limit itself is inside the accepted range."""
    response = client_for(make_user()).post(LIST, json=create_body(**{field: value}))

    assert response.status_code == 201, response.text
    assert response.json()[field] == value


@pytest.mark.parametrize(
    ("field", "body"),
    [
        ("title", create_body(title="t" * 201)),
        ("title", create_body(title="")),
        ("title", {k: v for k, v in create_body().items() if k != "title"}),
        ("description", create_body(description="d" * 10001)),
        ("description", create_body(description="")),
        (
            "description",
            {k: v for k, v in create_body().items() if k != "description"},
        ),
        ("priority", create_body(priority="urgent")),
        ("priority", {k: v for k, v in create_body().items() if k != "priority"}),
    ],
)
def test_create_rejects_invalid_fields(field, body, make_user, client_for):
    """SR-7, SR-8, SR-9 — 422 with the offending field named in `fields`."""
    response = client_for(make_user()).post(LIST, json=body)

    error = assert_envelope(response, 422, "VALIDATION_ERROR")
    assert field in error["fields"], error["fields"]


@pytest.mark.parametrize("priority", ["low", "medium", "high"])
def test_create_accepts_every_priority(priority, make_user, client_for):
    """SR-6 — all three documented values are accepted and stored."""
    response = client_for(make_user()).post(
        LIST, json=create_body(priority=priority)
    )

    assert response.status_code == 201, response.text
    assert response.json()["priority"] == priority


# --- POST /service-requests: server-controlled fields (SR-10, XC-8) ----------


def test_create_ignores_client_supplied_server_fields(
    make_user, client_for, db_session, status_by_name
):
    """SR-10 / XC-8 — supplying all three changes nothing about the outcome.

    The requirement is specifically *ignore*, not *reject*: a 422 here would
    also stop the value being applied, and would still be a contract break,
    because XC-8 says a field documented as "not accepted" must not change what
    happens.
    """
    owner = make_user()
    impostor = make_user()
    closed = status_by_name("closed")

    response = client_for(owner).post(
        LIST,
        json=create_body(
            requestor_id=str(impostor.id),
            request_type="hardware",
            current_status_id=str(closed.id),
        ),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["requestor"]["id"] == str(owner.id)
    assert body["request_type"] == "general"
    assert body["status"]["name"] == "open"

    row = db_session.get(ServiceRequest, uuid.UUID(body["id"]))
    assert row.requestor_id == owner.id
    assert row.request_type == "general"
    assert row.current_status_id != closed.id


# --- POST /service-requests: initial history row (SR-14) ---------------------


def test_create_writes_exactly_one_open_history_row(
    make_user, client_for, db_session, status_by_name
):
    """SR-14 — the request's history starts where the request does."""
    owner = make_user()

    body = client_for(owner).post(LIST, json=create_body()).json()

    rows = (
        db_session.execute(
            select(StatusHistory).where(
                StatusHistory.service_request_id == uuid.UUID(body["id"])
            )
        )
        .scalars()
        .all()
    )

    assert len(rows) == 1
    assert rows[0].status_id == status_by_name("open").id
    assert rows[0].changed_by_id == owner.id


def test_create_writes_nothing_when_the_history_insert_fails(
    monkeypatch, make_user, client_for, db_session
):
    """SR-14 — atomicity, proven by observing the failure.

    A green success path shows the two rows arriving together; it cannot show
    that they *must*. Only forcing the second write to fail and finding no
    first row does that, which is backend/CLAUDE.md's "verify it can fail" rule
    applied to a transaction boundary rather than to a constraint.
    """
    owner = make_user()
    doomed_title = f"atomicity-{uuid.uuid4().hex[:12]}"

    def _sabotaged_history(**kwargs: object) -> StatusHistory:
        # A status_id matching no `statuses` row: the INSERT fails on its
        # foreign key at flush time — mid-transaction, the way a real failure
        # would, rather than before any SQL has been emitted.
        return StatusHistory(**{**kwargs, "status_id": uuid.uuid4()})

    monkeypatch.setattr(
        service_requests_module, "StatusHistory", _sabotaged_history
    )

    response = client_for(owner, raise_server_exceptions=False).post(
        LIST, json=create_body(title=doomed_title)
    )

    assert_envelope(response, 500, "INTERNAL_ERROR")

    db_session.rollback()
    orphan = db_session.execute(
        select(ServiceRequest).where(ServiceRequest.title == doomed_title)
    ).first()
    assert orphan is None, "the request survived a failed history insert"


# --- GET /service-requests/{id} (SR-11 .. SR-13) -----------------------------


def test_owner_can_fetch_their_request(make_user, make_service_request, client_for):
    """SR-11 — the requestor sees their own row."""
    owner = make_user()
    request = make_service_request(owner)

    response = client_for(owner).get(detail(request.id))

    assert response.status_code == 200, response.text
    assert response.json()["id"] == str(request.id)


def test_admin_can_fetch_anyones_request(
    make_user, make_service_request, client_for
):
    """SR-11 — an admin's visibility is not limited to their own rows."""
    admin = make_user(role="admin")
    request = make_service_request(make_user())

    response = client_for(admin).get(detail(request.id))

    assert response.status_code == 200, response.text
    assert response.json()["id"] == str(request.id)


def test_unknown_id_forms_are_indistinguishable(
    make_user, make_service_request, client_for
):
    """SR-12 / SR-13 / XC-7 — three different causes, one identical answer.

    Someone else's request, a well-formed id that matches nothing, and a string
    that is not an id at all must not be tellable apart. A 403 on the first
    would confirm the id exists; a 422 on the third would confirm the other two
    are at least *shaped* like real ids.
    """
    caller = make_user()
    someone_elses = make_service_request(make_user())
    client = client_for(caller)

    responses = [
        client.get(detail(someone_elses.id)),
        client.get(detail(uuid.uuid4())),
        client.get(detail("not-a-uuid")),
    ]

    for response in responses:
        assert_envelope(response, 404, "NOT_FOUND")
    assert len({response.content for response in responses}) == 1
    assert len({response.status_code for response in responses}) == 1


def test_detail_carries_the_same_shape_as_a_list_item(
    make_user, make_service_request, client_for
):
    """design.md §0 decision 2 — one shape, so detail adds no keys of its own."""
    owner = make_user()
    request = make_service_request(owner)
    client = client_for(owner)

    from_list = client.get(LIST).json()["items"][0]
    from_detail = client.get(detail(request.id)).json()

    assert from_list == from_detail


# --- AUTH-5 / XC-15 ----------------------------------------------------------


def test_no_response_carries_a_password_field(
    make_user, make_service_request, client_for
):
    """AUTH-5 / XC-15 — including on an error path, not only on 2xx.

    Every user in these payloads serialises through `UserSummary`, which has no
    such field to expose. The error response is in the list on purpose: it is
    the path a success-path test never covers and the one where a handler
    rendering an exception's own text would leak the row it was excluding.
    """
    owner = make_user()
    request = make_service_request(owner)
    client = client_for(owner)

    for response in (
        client.get(LIST),
        client.get(detail(request.id)),
        client.post(LIST, json=create_body()),
        client.get(detail("not-a-uuid")),
        client.get(LIST, params={"status": "in_limbo"}),
    ):
        assert_no_password(response)


# --- N+1 ---------------------------------------------------------------------


def test_list_statement_count_does_not_grow_with_rows(
    engine, db_session, make_user, make_service_request, client_for, status_by_name
):
    """The eager loads, asserted as a property rather than as a number.

    Lazy-loading `status`, `requestor` and `assignee` costs 1 + 3n statements
    for a page of n, and every correctness test in this file passes either way
    — the payload is identical, just assembled far more expensively. Comparing
    two row counts is what makes the growth visible; a "fewer than N" bound
    would be satisfied by an N+1 on a small enough page.

    **Two things in the obvious version of this test make it pass with the
    joinedloads removed**, and both had to be designed out. This task's
    mutation pass is what found them:

    * The rows are seeded through the very session the request handler then
      uses, so every related object is already in SQLAlchemy's identity map
      and a lazy many-to-one load is answered from memory without touching the
      database. `expunge_all()` before each measured call empties it — which is
      not a trick to make the test fail, it is what restores the production
      condition: `get_db` yields a *fresh* session per request, so the identity
      map there is always cold.
    * Every row sharing one requestor and one status makes the N+1 self-limit
      at two queries no matter how many rows there are, because the second row
      finds the first row's objects already loaded. So each row here gets its
      own requestor and its own assignee, and the statuses are spread across
      all four seeded rows.

    The assignee is populated only here. Nothing in this phase writes one
    (design.md §7), so leaving it null everywhere would leave that joinedload
    permanently unexercised — a `NULL` foreign key is not lazily loaded at all,
    and its eager load could be deleted with nothing noticing.
    """
    admin = make_user(role="admin")
    statuses = [
        status_by_name(name)
        for name in ("open", "in_progress", "resolved", "closed")
    ]
    # Built before the first `expunge_all` — it reads `admin.id` and
    # `admin.role` to mint the token, which a detached instance would not
    # answer for.
    client = client_for(admin)

    def seed(count: int, *, offset: int) -> None:
        for index in range(count):
            make_service_request(
                make_user(),
                assignee=make_user(),
                current_status_id=statuses[(index + offset) % len(statuses)].id,
            )

    def statements_for(expected_rows: int) -> int:
        db_session.expunge_all()
        with statement_counter(engine) as statements:
            body = client.get(LIST, params={"page_size": 100}).json()
            assert len(body["items"]) == expected_rows, body["total"]
            return len(statements)

    seed(3, offset=0)
    few_rows = statements_for(3)

    seed(12, offset=3)
    many_rows = statements_for(15)

    assert few_rows == many_rows, (
        f"{few_rows} statements for 3 rows, {many_rows} for 15 — the per-row "
        "queries are the lazy loads the joinedloads exist to prevent"
    )
