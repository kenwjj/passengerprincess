"""Trip + membership persistence; itinerary stored as a JSON blob."""

from __future__ import annotations

import sqlite3


def create_trip(
    conn: sqlite3.Connection,
    *,
    creator_id: int,
    destination: str,
    start_date: str,
    end_date: str,
    activity: str,
    now: str,
) -> int:
    """Insert a new trip row (itinerary unset) and return its id."""
    cur = conn.execute(
        """
        INSERT INTO trips
            (creator_id, destination, start_date, end_date, activity, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (creator_id, destination, start_date, end_date, activity, now),
    )
    conn.commit()
    return int(cur.lastrowid)


def add_member(conn: sqlite3.Connection, trip_id: int, user_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO trip_members (trip_id, telegram_user_id) VALUES (?, ?)",
        (trip_id, user_id),
    )
    conn.commit()


def get_members(conn: sqlite3.Connection, trip_id: int) -> list[int]:
    cur = conn.execute(
        "SELECT telegram_user_id FROM trip_members WHERE trip_id = ?", (trip_id,)
    )
    return [row["telegram_user_id"] for row in cur.fetchall()]


def save_itinerary(conn: sqlite3.Connection, trip_id: int, itinerary_json: str) -> None:
    conn.execute(
        "UPDATE trips SET itinerary_json = ? WHERE id = ?", (itinerary_json, trip_id)
    )
    conn.commit()


def get_trip(conn: sqlite3.Connection, trip_id: int) -> sqlite3.Row | None:
    cur = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,))
    return cur.fetchone()


def list_trips_for_user(conn: sqlite3.Connection, user_id: int) -> list[sqlite3.Row]:
    """Trips the user created OR is a member of, newest first."""
    cur = conn.execute(
        """
        SELECT * FROM trips
        WHERE creator_id = ?
           OR id IN (SELECT trip_id FROM trip_members WHERE telegram_user_id = ?)
        ORDER BY id DESC
        """,
        (user_id, user_id),
    )
    return cur.fetchall()
