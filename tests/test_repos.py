import sqlite3

import pytest

from src import db
from src.repos import answers as answers_repo
from src.repos import users as users_repo

NOW = "2026-05-30T12:00:00"


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


def test_upsert_user_inserts_then_updates(conn):
    users_repo.upsert_user(conn, 1, username="ken", first_name="Ken", now=NOW)
    row = users_repo.get_user(conn, 1)
    assert row["first_name"] == "Ken"
    assert row["completed_at"] is None

    # Re-upsert updates profile fields, preserves created_at.
    users_repo.upsert_user(conn, 1, username="ken2", first_name="Kenneth", now="later")
    row = users_repo.get_user(conn, 1)
    assert row["first_name"] == "Kenneth"
    assert row["created_at"] == NOW


def test_get_user_missing_returns_none(conn):
    assert users_repo.get_user(conn, 999) is None


def test_set_completed_at(conn):
    users_repo.upsert_user(conn, 1, username=None, first_name="K", now=NOW)
    users_repo.set_completed_at(conn, 1, when="2026-05-30T12:05:00")
    assert users_repo.get_user(conn, 1)["completed_at"] == "2026-05-30T12:05:00"


def test_answer_upsert_overwrites_on_reanswer(conn):
    answers_repo.upsert_answer(conn, 1, "food_adventure", "ramen", now=NOW)
    answers_repo.upsert_answer(conn, 1, "food_adventure", "sushi", now=NOW)
    assert answers_repo.get_answers(conn, 1) == {"food_adventure": "sushi"}


def test_get_answers_returns_map(conn):
    answers_repo.upsert_answer(conn, 1, "food_adventure", "ramen", now=NOW)
    answers_repo.upsert_answer(conn, 1, "drink", "coffee", now=NOW)
    assert answers_repo.get_answers(conn, 1) == {
        "food_adventure": "ramen",
        "drink": "coffee",
    }


def test_clear_answers_and_reset_completion(conn):
    users_repo.upsert_user(conn, 1, username=None, first_name="K", now=NOW)
    users_repo.set_completed_at(conn, 1, when=NOW)
    answers_repo.upsert_answer(conn, 1, "drink", "coffee", now=NOW)

    answers_repo.clear_answers(conn, 1)

    assert answers_repo.get_answers(conn, 1) == {}
    assert users_repo.get_user(conn, 1)["completed_at"] is None
