import sqlite3

import pytest

from src import db
from src.repos import trips as trips_repo
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


def _make_trip(conn, creator_id=1):
    return trips_repo.create_trip(
        conn,
        creator_id=creator_id,
        destination="Jeju",
        start_date="2026-10-24",
        end_date="2026-10-28",
        activity="cycling",
        now=NOW,
    )


def test_create_trip_and_get(conn):
    trip_id = _make_trip(conn)
    row = trips_repo.get_trip(conn, trip_id)
    assert row["destination"] == "Jeju"
    assert row["activity"] == "cycling"
    assert row["itinerary_json"] is None


def test_add_and_get_members(conn):
    trip_id = _make_trip(conn)
    trips_repo.add_member(conn, trip_id, 1)
    trips_repo.add_member(conn, trip_id, 2)
    trips_repo.add_member(conn, trip_id, 2)  # idempotent
    assert sorted(trips_repo.get_members(conn, trip_id)) == [1, 2]


def test_save_itinerary_blob(conn):
    trip_id = _make_trip(conn)
    trips_repo.save_itinerary(conn, trip_id, '{"trip_summary": "x", "days": []}')
    row = trips_repo.get_trip(conn, trip_id)
    assert row["itinerary_json"] == '{"trip_summary": "x", "days": []}'


def test_list_trips_for_user_includes_creator_and_member(conn):
    t1 = _make_trip(conn, creator_id=1)
    trips_repo.add_member(conn, t1, 1)
    trips_repo.add_member(conn, t1, 2)
    t2 = _make_trip(conn, creator_id=3)
    trips_repo.add_member(conn, t2, 2)  # user 2 is a member but not creator

    ids_for_2 = {r["id"] for r in trips_repo.list_trips_for_user(conn, 2)}
    assert ids_for_2 == {t1, t2}

    rows_for_1 = trips_repo.list_trips_for_user(conn, 1)
    assert {r["id"] for r in rows_for_1} == {t1}
    assert len(rows_for_1) == 1  # creator+member of t1 => single row, no dup
