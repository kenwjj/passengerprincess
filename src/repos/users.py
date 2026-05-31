"""User row persistence."""

from __future__ import annotations

import sqlite3


def upsert_user(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    username: str | None,
    first_name: str | None,
    now: str,
) -> None:
    conn.execute(
        """
        INSERT INTO users (telegram_user_id, username, first_name, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(telegram_user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name
        """,
        (user_id, username, first_name, now),
    )
    conn.commit()


def get_user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    cur = conn.execute("SELECT * FROM users WHERE telegram_user_id = ?", (user_id,))
    return cur.fetchone()


def set_completed_at(conn: sqlite3.Connection, user_id: int, *, when: str) -> None:
    conn.execute(
        "UPDATE users SET completed_at = ? WHERE telegram_user_id = ?",
        (when, user_id),
    )
    conn.commit()
