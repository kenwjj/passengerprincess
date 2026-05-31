"""SQLite connection + idempotent schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  telegram_user_id INTEGER PRIMARY KEY,
  username          TEXT,
  first_name        TEXT,
  created_at        TEXT NOT NULL,
  completed_at      TEXT
);

CREATE TABLE IF NOT EXISTS answers (
  telegram_user_id INTEGER NOT NULL,
  question_id      TEXT    NOT NULL,
  value            TEXT    NOT NULL,
  answered_at      TEXT    NOT NULL,
  PRIMARY KEY (telegram_user_id, question_id)
);

CREATE TABLE IF NOT EXISTS trips (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  creator_id     INTEGER NOT NULL,
  destination    TEXT    NOT NULL,
  start_date     TEXT    NOT NULL,
  end_date       TEXT    NOT NULL,
  activity       TEXT    NOT NULL,
  itinerary_json TEXT,
  created_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS trip_members (
  trip_id          INTEGER NOT NULL,
  telegram_user_id INTEGER NOT NULL,
  PRIMARY KEY (trip_id, telegram_user_id)
);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def connect(path: str | Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn
