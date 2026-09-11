"""``GET /statuses`` (T-SR-0; ST-1, ST-2).

Contract tests against the real Postgres test database and the real
``create_app()`` (backend/CLAUDE.md). The four rows under test are seeded by
the reference-data migration, so this suite reads what a deployed database
would actually serve rather than rows a fixture invented.
"""

from __future__ import annotations

STATUSES = "/api/v1/statuses"

# ST-2's four rows, in the order the requirement names them. Written out rather
# than read back from the `statuses` table: deriving the expectation from the
# same rows the endpoint returns would assert only that the endpoint agrees
# with itself, which is the failure family backend/CLAUDE.md's testing section
# records three instances of.
EXPECTED = [
    ("open", 1, False),
    ("in_progress", 2, False),
    ("resolved", 3, True),
    ("closed", 4, True),
]


def test_requires_no_authentication(client):
    """ST-1 — no cookie, no 401. The stepper renders for signed-out pages too."""
    response = client.get(STATUSES)

    assert response.status_code == 200, response.text
    assert "error" not in response.json()


def test_returns_the_four_seeded_rows_in_sort_order(client):
    """ST-2 — all four, ascending by `sort_order`, not by name or insertion."""
    items = client.get(STATUSES).json()["items"]

    assert [
        (item["name"], item["sort_order"], item["is_terminal"]) for item in items
    ] == EXPECTED


def test_item_shape_matches_the_contract(client):
    """design.md §1's `Status` object — exactly these four keys."""
    items = client.get(STATUSES).json()["items"]

    for item in items:
        assert set(item) == {"id", "name", "sort_order", "is_terminal"}
        # XC-3: UUID strings, no sequential identifier.
        assert isinstance(item["id"], str) and len(item["id"]) == 36


def test_body_is_not_the_paginated_envelope(client):
    """ST-2 — a bare `{"items": [...]}`, deliberately not XC-10's envelope."""
    body = client.get(STATUSES).json()

    assert set(body) == {"items"}
