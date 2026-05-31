import sqlite3

import pytest

from src import db
from src.repos import users as users_repo

NOW = "2026-05-31T12:00:00"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.init_schema(c)
    yield c
    c.close()


def test_schema_creates_trip_tables(conn):
    names = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"trips", "trip_members"} <= names


def test_list_completed_users_only_returns_finished(conn):
    users_repo.upsert_user(conn, 1, username="ken", first_name="Ken", now=NOW)
    users_repo.upsert_user(conn, 2, username="amy", first_name="Amy", now=NOW)
    users_repo.set_completed_at(conn, 1, when=NOW)  # only user 1 finished

    rows = users_repo.list_completed_users(conn)

    assert [r["telegram_user_id"] for r in rows] == [1]
    assert rows[0]["first_name"] == "Ken"
