import sqlite3

import pytest

from src import db

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
