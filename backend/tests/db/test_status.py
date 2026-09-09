"""Schema contract test for the ``statuses`` table (app/db/models/status.py).

Covers Task 6 / R10 category 5: after migration, the four seed rows from R3
exist with exactly the specified ``sort_order`` / ``is_terminal`` values —
seeded by the ``80919378ee7a_seed_statuses`` data migration.
"""

from sqlalchemy import select

from app.db.models import Status

# (name, sort_order, is_terminal) exactly as specified by R3 / design.md.
EXPECTED_SEED = [
    ("open", 1, False),
    ("in_progress", 2, False),
    ("resolved", 3, True),
    ("closed", 4, True),
]


def test_seed_statuses_match_r3(db_session):
    rows = (
        db_session.execute(select(Status).order_by(Status.sort_order))
        .scalars()
        .all()
    )
    actual = [(r.name, r.sort_order, r.is_terminal) for r in rows]
    assert actual == EXPECTED_SEED
