"""Schema-wide contract tests that aren't tied to a single model.

Covers, from Task 6 / R10:

* category 4 — migration round-trip: ``upgrade head`` -> ``downgrade base`` ->
  ``upgrade head`` all succeed, run against ``TEST_DATABASE_URL`` (never dev).
* A cross-cutting check that every timestamp column across all six tables is
  ``timestamp with time zone`` (TIMESTAMPTZ), per R1 / design.md and the
  Task 5 spot-check note.

``test_migration_round_trip`` deliberately does **not** use the ``db_session``
transaction wrapper: its whole point is to apply and revert real migrations.
It drives the test database down to empty and back to ``head``, so it leaves
the schema exactly where it found it (including the re-seeded ``statuses``).
"""

from alembic import command
from sqlalchemy import text

# table -> the timestamp columns design.md's DDL declares as TIMESTAMPTZ.
EXPECTED_TZ_COLUMNS = {
    "users": {"created_at", "updated_at"},
    "service_requests": {"created_at", "updated_at"},
    "comments": {"created_at", "updated_at"},
    "status_history": {"changed_at"},
    "refresh_tokens": {"created_at", "expires_at", "revoked_at"},
}


def test_migration_round_trip(alembic_config):
    # Each command raises on failure, so reaching the end == success.
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")


def test_all_timestamp_columns_are_timestamptz(engine):
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND (data_type LIKE 'timestamp%' OR data_type LIKE 'time %')
                """
            )
        ).all()

    found = {(t, c): d for t, c, d in rows}

    for table, columns in EXPECTED_TZ_COLUMNS.items():
        for column in columns:
            assert found.get((table, column)) == "timestamp with time zone", (
                f"{table}.{column} is {found.get((table, column))!r}, "
                "expected 'timestamp with time zone'"
            )

    naive = {k: v for k, v in found.items() if v != "timestamp with time zone"}
    assert not naive, f"naive timestamp column(s) found: {naive}"
