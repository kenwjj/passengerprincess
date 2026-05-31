"""Answer persistence (key-value per user/question)."""

from __future__ import annotations

import sqlite3


def upsert_answer(
    conn: sqlite3.Connection,
    user_id: int,
    question_id: str,
    value: str,
    *,
    now: str,
) -> None:
    conn.execute(
        """
        INSERT INTO answers (telegram_user_id, question_id, value, answered_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(telegram_user_id, question_id) DO UPDATE SET
            value = excluded.value,
            answered_at = excluded.answered_at
        """,
        (user_id, question_id, value, now),
    )
    conn.commit()


def get_answers(conn: sqlite3.Connection, user_id: int) -> dict[str, str]:
    cur = conn.execute(
        "SELECT question_id, value FROM answers WHERE telegram_user_id = ?",
        (user_id,),
    )
    return {row["question_id"]: row["value"] for row in cur.fetchall()}


def clear_answers(conn: sqlite3.Connection, user_id: int) -> None:
    """Delete all answers and reset the user's completion flag (used by /start and /restart)."""
    conn.execute("DELETE FROM answers WHERE telegram_user_id = ?", (user_id,))
    conn.execute(
        "UPDATE users SET completed_at = NULL WHERE telegram_user_id = ?",
        (user_id,),
    )
    conn.commit()
