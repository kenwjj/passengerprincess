import sqlite3

import pytest

from src import db


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.init_schema(c)
    yield c
    c.close()


def test_init_schema_creates_tables(conn):
    names = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"users", "answers"} <= names


def test_init_schema_is_idempotent(conn):
    # Running twice must not raise.
    db.init_schema(conn)
    db.init_schema(conn)
