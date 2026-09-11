"""The two comment endpoints (T-CM-0; CM-1 .. CM-9, XC-5, XC-7, XC-10).

Contract tests against the real Postgres test database and the real
``create_app()`` (backend/CLAUDE.md) — no SQLite, no hand-assembled app.

Error assertions check the whole envelope, not the status code alone.

Three of these are written to fail for a specific reason rather than to
describe a feature, and are worth reading as such:
``test_user_never_receives_an_internal_comment`` is what catches an internal
comment filtered in Python instead of in SQL,
``test_create_404_precedes_body_validation`` is what catches the visibility
check written as the handler's first statement rather than as a dependency,
and ``test_list_statement_count_does_not_grow_with_rows`` is what catches the
lazy-loaded ``author`` that no correctness assertion would ever notice.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine

from app.db.models import Comment

REQUESTS = "/api/v1/service-requests"

# A fixed instant, so "oldest first" is a property of the data rather than of
# how fast the test ran. Postgres' `now()` is transaction-scoped, so rows
# seeded in one test would otherwise all share a created_at by accident — which
# would make the ordering assertions pass without ordering by created_at at all.
BASE_TIME = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)


def comments_url(request_id: object) -> str:
    return f"{REQUESTS}/{request_id}/comments"


def create_body(**overrides: object) -> dict[str, object]:
    """A valid `POST .../comments` body (design.md §6)."""
    body: dict[str, object] = {"body": "Any update on this?"}
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


@pytest.fixture
def make_comment(db_session):
    """A comment row factory. Everything rolls back, so it needs no cleanup."""

    def _make(request, author, **overrides: object) -> Comment:
        fields: dict[str, object] = dict(
            service_request_id=request.id,
            author_id=author.id,
            body="Please try restarting your VPN client.",
        )
        fields.update(overrides)
        comment = Comment(**fields)
        db_session.add(comment)
        db_session.flush()
        return comment

    return _make


# --- XC-5 / T-DEBT-4: both routes are gated ----------------------------------


@pytest.mark.parametrize(
    ("method", "kwargs"),
    [
        ("get", {}),
        # The CSRF header is sent so XC-9's 403 can't stand in for the 401 under
        # test — this asserts the auth gate, not the middleware in front of it.
        ("post", {"json": create_body(), "headers": {"X-Requested-With": "x"}}),
    ],
)
def test_requires_a_session(method, kwargs, make_user, make_service_request, client):
    """XC-5, and T-DEBT-4's first item, for the comment routes.

    T-DEBT-4 flags exactly this: `XC-5` was proven generically in `T-AUTH-2`
    against a throwaway route, and every other test in this file authenticates,
    so a route declared without `get_current_user` would pass all of them. The
    gate is asserted here directly rather than trusted to fail by side effect —
    and that side effect is genuinely absent on the list route, where the
    caller is used only to decide which comments they may see. Drop the
    dependency and an unauthenticated caller doesn't crash; they get someone
    else's comments.
    """
    request = make_service_request(make_user())

    response = getattr(client, method)(comments_url(request.id), **kwargs)

    assert_envelope(response, 401, "UNAUTHENTICATED")


# --- GET: the internal-comment audience (CM-2, CM-3) -------------------------


def test_user_never_receives_an_internal_comment(
    make_user, make_service_request, make_comment, client_for
):
    """CM-2 — checked against the raw JSON, not against what a UI would draw.

    design.md §6 calls this a trust boundary: a comment the server sent and the
    client chose not to display is still a comment the requestor can read in
    devtools. So the assertion is on the response body and on `total`, the two
    places a row that was fetched-then-hidden would still show up.

    Both halves are non-empty on purpose — a version of this test where the
    request happened to have no public comment would pass while proving only
    that an empty list contains nothing.
    """
    owner = make_user()
    admin = make_user(role="admin")
    request = make_service_request(owner)
    public = make_comment(request, admin, body="We are looking into it.")
    internal = make_comment(
        request, admin, body="Check the VPN concentrator logs.", is_internal=True
    )

    response = client_for(owner).get(comments_url(request.id))

    assert response.status_code == 200, response.text
    body = response.json()
    returned = [item["id"] for item in body["items"]]
    assert returned == [str(public.id)]
    assert str(internal.id) not in response.text
    assert internal.body not in response.text
    # A `total` of 2 would mean the row was counted and then dropped — which is
    # the same leak in a smaller form, and the half a list-of-ids assertion
    # misses.
    assert body["total"] == 1


def test_admin_receives_internal_comments(
    make_user, make_service_request, make_comment, client_for
):
    """CM-3 — an admin sees both kinds, with `is_internal` on each."""
    admin = make_user(role="admin")
    request = make_service_request(make_user())
    public = make_comment(request, admin)
    internal = make_comment(request, admin, is_internal=True)

    body = client_for(admin).get(comments_url(request.id)).json()

    by_id = {item["id"]: item for item in body["items"]}
    assert set(by_id) == {str(public.id), str(internal.id)}
    assert by_id[str(public.id)]["is_internal"] is False
    assert by_id[str(internal.id)]["is_internal"] is True
    assert body["total"] == 2


# --- GET: scope, shape, ordering, paging (CM-1, XC-10) -----------------------


def test_list_is_scoped_to_its_parent_request(
    make_user, make_service_request, make_comment, client_for
):
    """CM-1 — a sub-resource returns its own parent's rows and no others."""
    owner = make_user()
    mine = make_service_request(owner)
    other = make_service_request(owner)
    on_mine = make_comment(mine, owner, body="On the right request.")
    on_other = make_comment(other, owner, body="On the wrong request.")

    body = client_for(owner).get(comments_url(mine.id)).json()

    assert [item["id"] for item in body["items"]] == [str(on_mine.id)]
    assert str(on_other.id) not in body["items"][0]["id"]
    assert body["total"] == 1


def test_comment_shape_matches_the_contract(
    make_user, make_service_request, make_comment, client_for
):
    """design.md §6's `Comment`, field for field."""
    owner = make_user()
    request = make_service_request(owner)
    comment = make_comment(request, owner)

    item = client_for(owner).get(comments_url(request.id)).json()["items"][0]

    assert set(item) == {
        "id",
        "author",
        "body",
        "is_internal",
        "created_at",
        "updated_at",
    }
    # design.md §0 decision 4: a structured user summary, never a pre-formatted
    # display string like the prototype's `'Priya Nair — IT Service Desk'`.
    assert set(item["author"]) == {"id", "first_name", "last_name", "role"}
    assert item["author"]["id"] == str(owner.id)
    assert item["id"] == str(comment.id)
    # XC-2: ISO 8601, UTC, explicit offset.
    assert item["created_at"].endswith("Z")
    assert item["updated_at"].endswith("Z")


def test_list_envelope_shape(make_user, make_service_request, client_for):
    """XC-10 — the four envelope keys, with the documented defaults."""
    owner = make_user()
    request = make_service_request(owner)

    body = client_for(owner).get(comments_url(request.id)).json()

    assert set(body) == {"items", "total", "page", "page_size"}
    assert body["items"] == []
    assert body["total"] == 0
    assert body["page"] == 1
    assert body["page_size"] == 20


def test_oldest_first(make_user, make_service_request, make_comment, client_for):
    """CM-1 — `created_at` ascending, the opposite of the request list's order.

    A conversation reads forwards; SR-15's list reads newest-first because it
    is an inbox. Asserted rather than assumed because the two endpoints sit in
    the same API and the wrong one is a plausible copy.
    """
    owner = make_user()
    request = make_service_request(owner)
    oldest = make_comment(request, owner, created_at=BASE_TIME)
    middle = make_comment(request, owner, created_at=BASE_TIME.replace(hour=10))
    newest = make_comment(request, owner, created_at=BASE_TIME.replace(hour=11))

    items = client_for(owner).get(comments_url(request.id)).json()["items"]

    assert [item["id"] for item in items] == [
        str(oldest.id),
        str(middle.id),
        str(newest.id),
    ]


def test_identical_timestamps_order_by_id_and_stay_stable(
    make_user, make_service_request, make_comment, client_for
):
    """CM-1 — `id` ascending breaks a `created_at` tie, repeatably.

    Comments sharing a timestamp are not hypothetical: `now()` is
    transaction-wide in Postgres. Without a tiebreaker the database may return
    equal-keyed rows in any order it likes, which under paging means a comment
    can appear on two pages or on none.
    """
    owner = make_user()
    request = make_service_request(owner)
    expected = sorted(
        str(make_comment(request, owner, created_at=BASE_TIME).id) for _ in range(5)
    )

    client = client_for(owner)
    first = [item["id"] for item in client.get(comments_url(request.id)).json()["items"]]
    second = [
        item["id"] for item in client.get(comments_url(request.id)).json()["items"]
    ]

    assert first == expected
    assert second == expected


def test_paging_walks_the_rows_without_overlap(
    make_user, make_service_request, make_comment, client_for
):
    """XC-10 — `page` is 1-based and pages don't repeat rows."""
    owner = make_user()
    request = make_service_request(owner)
    for index in range(5):
        make_comment(request, owner, created_at=BASE_TIME.replace(minute=index))

    client = client_for(owner)
    first = client.get(comments_url(request.id), params={"page": 1, "page_size": 2})
    second = client.get(comments_url(request.id), params={"page": 2, "page_size": 2})

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
        .get(comments_url(request.id), params={"page_size": 250})
        .json()
    )

    assert body["page_size"] == 100


# --- GET: parent visibility (CM-4) -------------------------------------------


def test_list_404s_for_a_parent_the_caller_cannot_see(
    make_user, make_service_request, client_for
):
    """CM-4 / XC-7 — three different causes, one identical answer.

    Someone else's request, a well-formed id that matches nothing, and a string
    that is not an id at all must not be tellable apart, and must match SR-12's
    answer on the parent route itself. A 403 on the first would confirm the
    request exists; a 422 on the third would confirm the other two are at least
    *shaped* like real ids.
    """
    caller = make_user()
    someone_elses = make_service_request(make_user())
    client = client_for(caller)

    responses = [
        client.get(comments_url(someone_elses.id)),
        client.get(comments_url(uuid.uuid4())),
        client.get(comments_url("not-a-uuid")),
        # The parent route's own 404, which these must be identical to — the
        # whole point of CM-4 citing SR-12 rather than restating it.
        client.get(f"{REQUESTS}/{someone_elses.id}"),
    ]

    for response in responses:
        assert_envelope(response, 404, "NOT_FOUND")
    assert len({response.content for response in responses}) == 1


def test_admin_can_read_any_requests_comments(
    make_user, make_service_request, make_comment, client_for
):
    """CM-4 inherits SR-11: an admin's visibility is not limited to their own."""
    admin = make_user(role="admin")
    request = make_service_request(make_user())
    comment = make_comment(request, make_user())

    body = client_for(admin).get(comments_url(request.id)).json()

    assert [item["id"] for item in body["items"]] == [str(comment.id)]


# --- POST: creating a comment (CM-5, CM-6) -----------------------------------


def test_create_returns_the_created_comment(
    make_user, make_service_request, client_for, db_session
):
    """CM-5 — a 201 carrying the created row, authored by the caller."""
    owner = make_user()
    request = make_service_request(owner)

    response = client_for(owner).post(
        comments_url(request.id), json=create_body(body="Any update on this?")
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["body"] == "Any update on this?"
    assert body["author"]["id"] == str(owner.id)
    assert body["is_internal"] is False

    # Read back through the database rather than trusting the response to
    # describe what was stored.
    row = db_session.get(Comment, uuid.UUID(body["id"]))
    assert row is not None
    assert row.service_request_id == request.id
    assert row.author_id == owner.id
    assert row.is_internal is False


def test_created_comment_appears_in_the_list(
    make_user, make_service_request, client_for
):
    """CM-5 + CM-1 — the write is visible to the read, same shape either way."""
    owner = make_user()
    request = make_service_request(owner)
    client = client_for(owner)

    created = client.post(comments_url(request.id), json=create_body()).json()
    listed = client.get(comments_url(request.id)).json()["items"]

    assert listed == [created]


def test_create_accepts_the_boundary_length(
    make_user, make_service_request, client_for
):
    """CM-6 — 5000 characters is inside the accepted range, not past it."""
    owner = make_user()
    request = make_service_request(owner)
    at_the_limit = "c" * 5000

    response = client_for(owner).post(
        comments_url(request.id), json=create_body(body=at_the_limit)
    )

    assert response.status_code == 201, response.text
    assert response.json()["body"] == at_the_limit


@pytest.mark.parametrize(
    "body",
    [
        create_body(body="c" * 5001),
        create_body(body=""),
        {},
        create_body(body=None),
    ],
    ids=["too-long", "empty", "missing", "null"],
)
def test_create_rejects_an_invalid_body(
    body, make_user, make_service_request, client_for
):
    """CM-6 — 422 with `fields.body` populated, not a bare status code."""
    owner = make_user()
    request = make_service_request(owner)

    response = client_for(owner).post(comments_url(request.id), json=body)

    error = assert_envelope(response, 422, "VALIDATION_ERROR")
    assert set(error["fields"]) == {"body"}, error["fields"]


# --- POST: the internal-comment permission (CM-7, CM-8) ----------------------


def test_user_posting_an_internal_comment_is_refused(
    make_user, make_service_request, client_for, db_session
):
    """CM-7 — 403, and no row, rather than a comment silently made public.

    The "no row" half is the one worth having. A handler that raised *after*
    adding the comment to the session would still answer 403 and would still
    leave a public comment behind under the caller's name — a response-code
    assertion alone cannot tell the two apart.
    """
    owner = make_user()
    request = make_service_request(owner)

    response = client_for(owner).post(
        comments_url(request.id), json=create_body(is_internal=True)
    )

    error = assert_envelope(response, 403, "FORBIDDEN")
    # design.md §1 reserves `fields` for VALIDATION_ERROR: this is a permission
    # the caller lacks, not a field they typed wrongly.
    assert "fields" not in error

    db_session.rollback()
    count = db_session.execute(
        select(func.count())
        .select_from(Comment)
        .where(Comment.service_request_id == request.id)
    ).scalar_one()
    assert count == 0, "the comment was created despite the 403"


def test_user_may_post_a_public_comment_explicitly(
    make_user, make_service_request, client_for
):
    """CM-7 is about `true` only — `is_internal: false` from a user is fine.

    Worth asserting separately: a check written against the field's *presence*
    rather than its value would reject this and would still pass the 403 test
    above.
    """
    owner = make_user()
    request = make_service_request(owner)

    response = client_for(owner).post(
        comments_url(request.id), json=create_body(is_internal=False)
    )

    assert response.status_code == 201, response.text
    assert response.json()["is_internal"] is False


@pytest.mark.parametrize("is_internal", [True, False])
def test_admin_can_post_either_kind(
    is_internal, make_user, make_service_request, client_for, db_session
):
    """CM-8 — an admin may set `is_internal` to either value."""
    admin = make_user(role="admin")
    request = make_service_request(make_user())

    response = client_for(admin).post(
        comments_url(request.id), json=create_body(is_internal=is_internal)
    )

    assert response.status_code == 201, response.text
    assert response.json()["is_internal"] is is_internal
    row = db_session.get(Comment, uuid.UUID(response.json()["id"]))
    assert row.is_internal is is_internal


def test_is_internal_defaults_to_false_when_omitted(
    make_user, make_service_request, client_for
):
    """CM-8 — omitted means public, for an admin as much as for anyone."""
    admin = make_user(role="admin")
    request = make_service_request(make_user())

    response = client_for(admin).post(comments_url(request.id), json=create_body())

    assert response.status_code == 201, response.text
    assert response.json()["is_internal"] is False


# --- POST: parent visibility precedes everything (CM-9) ----------------------


def test_create_404s_for_a_parent_the_caller_cannot_see(
    make_user, make_service_request, client_for
):
    """CM-9 — the same three indistinguishable answers as the read path."""
    caller = make_user()
    someone_elses = make_service_request(make_user())
    client = client_for(caller)

    responses = [
        client.post(comments_url(someone_elses.id), json=create_body()),
        client.post(comments_url(uuid.uuid4()), json=create_body()),
        client.post(comments_url("not-a-uuid"), json=create_body()),
    ]

    for response in responses:
        assert_envelope(response, 404, "NOT_FOUND")
    assert len({response.content for response in responses}) == 1


@pytest.mark.parametrize(
    "body",
    [{}, create_body(body="c" * 5001), create_body(is_internal=True)],
    ids=["missing-body", "over-long-body", "internal-flag"],
)
def test_create_404_precedes_body_validation(
    body, make_user, make_service_request, client_for
):
    """CM-9 — "before evaluating `body` or `is_internal`", asserted literally.

    This is the test that pins the visibility check to a *dependency*. FastAPI
    resolves dependencies before it validates a request body, so the check has
    to live there: written as the handler's first statement it would run after
    Pydantic had already answered 422, and a caller who cannot see the request
    would learn it exists from the fact that the API critiqued their body
    instead of denying the resource. The `is_internal` case is the same point
    for CM-7's 403.
    """
    caller = make_user()
    someone_elses = make_service_request(make_user())

    response = client_for(caller).post(comments_url(someone_elses.id), json=body)

    assert_envelope(response, 404, "NOT_FOUND")


# --- XC-8: server-controlled fields ------------------------------------------


def test_create_ignores_a_client_supplied_author(
    make_user, make_service_request, client_for, db_session
):
    """XC-8 — `author_id` in the body changes nothing about the outcome.

    The requirement is specifically *ignore*, not *reject*: a 422 here would
    also stop the value being applied and would still be a contract break,
    because XC-8 says a field documented as "not accepted" must not change what
    happens.
    """
    owner = make_user()
    impostor = make_user()
    request = make_service_request(owner)

    response = client_for(owner).post(
        comments_url(request.id),
        json=create_body(author_id=str(impostor.id), service_request_id=str(uuid.uuid4())),
    )

    assert response.status_code == 201, response.text
    assert response.json()["author"]["id"] == str(owner.id)
    row = db_session.get(Comment, uuid.UUID(response.json()["id"]))
    assert row.author_id == owner.id
    assert row.service_request_id == request.id


# --- AUTH-5 / XC-15 ----------------------------------------------------------


def test_no_response_carries_a_password_field(
    make_user, make_service_request, make_comment, client_for
):
    """AUTH-5 / XC-15 — including on the error paths, not only on 2xx.

    Every user in these payloads serialises through `UserSummary`, which has no
    such field to expose. The error responses are in the list on purpose: they
    are the paths a success-path test never covers and the ones where a handler
    rendering an exception's own text would leak the row it was excluding.
    """
    owner = make_user()
    request = make_service_request(owner)
    make_comment(request, owner)
    client = client_for(owner)

    for response in (
        client.get(comments_url(request.id)),
        client.post(comments_url(request.id), json=create_body()),
        client.get(comments_url("not-a-uuid")),
        client.post(comments_url(request.id), json={}),
        client.post(comments_url(request.id), json=create_body(is_internal=True)),
    ):
        assert "password" not in response.text.lower(), response.text


# --- N+1 ---------------------------------------------------------------------


def test_list_statement_count_does_not_grow_with_rows(
    engine, db_session, make_user, make_service_request, make_comment, client_for
):
    """The `author` eager load, asserted as a property rather than as a number.

    Lazy-loading `author` costs 1 + n statements for a page of n, and every
    correctness test in this file passes either way — the payload is identical,
    just assembled far more expensively. Comparing two row counts is what makes
    the growth visible; a "fewer than N" bound would be satisfied by an N+1 on
    a small enough page.

    Two things in the obvious version of this test make it pass with the
    joinedload removed, and both are designed out here per `T-SR-0`'s finding:

    * The rows are seeded through the very session the request handler then
      uses, so every author is already in SQLAlchemy's identity map and a lazy
      many-to-one load is answered from memory without touching the database.
      `expunge_all()` empties it, which is not a trick to force a failure — it
      restores the production condition, where `get_db` yields a fresh session
      per request and the identity map is always cold.
    * Every comment sharing one author makes the N+1 self-limit at two queries
      no matter how many rows there are, because the second comment finds the
      first one's author already loaded. So each comment here gets its own.
    """
    admin = make_user(role="admin")
    request = make_service_request(make_user())
    # Built before the first `expunge_all` — it reads `admin.id` and
    # `admin.role` to mint the token, which a detached instance would not
    # answer for. The parent's id is read for the same reason.
    client = client_for(admin)
    parent_url = comments_url(request.id)

    def seed(count: int) -> None:
        for _ in range(count):
            make_comment(request, make_user())

    def statements_for(expected_rows: int) -> int:
        db_session.expunge_all()
        with statement_counter(engine) as statements:
            body = client.get(parent_url, params={"page_size": 100}).json()
            assert len(body["items"]) == expected_rows, body["total"]
            return len(statements)

    seed(3)
    few_rows = statements_for(3)

    seed(12)
    many_rows = statements_for(15)

    assert few_rows == many_rows, (
        f"{few_rows} statements for 3 comments, {many_rows} for 15 — the "
        "per-row queries are the lazy loads the joinedload exists to prevent"
    )
