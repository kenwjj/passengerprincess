# Phase 2A — Personalized Text Itinerary — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `/newtrip` (a DM wizard) and `/trips` so a creator can pick quiz-completed party members, give a destination/dates/activity, and receive a Claude Sonnet–generated, per-day text itinerary tuned to all party profiles, persisted and re-renderable.

**Architecture:** Extends Phase 1's pattern — pure, unit-tested logic (`prompt`, `schema`, `render`, `summary`, `wizard`, date validation) separated from the network layer (`llm/client.py`, `trip/generator.py`, `trip/dates.py`) and thin Telegram handlers (`trip/handlers.py`). Structured output is forced via an `emit_itinerary` tool call; the validated itinerary is stored as a JSON blob on a `trips` row.

**Tech Stack:** Python 3.11+, aiogram 3.x (long-polling, MemoryStorage FSM), stdlib `sqlite3`/`json`, `anthropic` SDK (Sonnet for itinerary generation), `python-dateutil` (date-range parsing), `pytest`, `uv`.

**Source spec:** `docs/superpowers/specs/2026-05-31-phase2a-itinerary-generator-design.md`

---

## File Structure

Created:
- `src/llm/__init__.py`, `src/llm/client.py` — Anthropic client factory (thin).
- `src/repos/trips.py` — trip + member persistence, itinerary blob.
- `src/profile/summary.py` — pure profile → compact prompt text.
- `src/trip/__init__.py`, `src/trip/states.py`, `src/trip/session.py`, `src/trip/wizard.py`, `src/trip/prompt.py`, `src/trip/schema.py`, `src/trip/dates.py`, `src/trip/generator.py`, `src/trip/render.py`, `src/trip/handlers.py`.
- Tests: `tests/test_trips_repo.py`, `tests/test_summary.py`, `tests/test_itinerary_schema.py`, `tests/test_prompt.py`, `tests/test_trip_render.py`, `tests/test_dates.py`, `tests/test_generator.py`, `tests/test_wizard.py`.

Modified:
- `pyproject.toml` — add `anthropic` + `python-dateutil` dependencies.
- `src/config.py` — `get_anthropic_key()`, `ITINERARY_MODEL`, `DEFAULT_SUNSET`. (`DATE_MODEL` is added in Task 1 but removed again in Task 10 once date parsing drops the LLM.)
- `src/db.py` — add `trips`, `trip_members` tables.
- `src/repos/users.py` — `list_completed_users()`.
- `src/quiz/handlers.py` — extend `/help` text.
- `src/bot.py` — build Anthropic client, include `trip.handlers.router`, inject client.
- `.env.example`, `README.md` — `ANTHROPIC_API_KEY` setup.

Conventions (match Phase 1): `from __future__ import annotations`; UTC ISO timestamps via a `_now()` helper in handlers; pure modules import no aiogram; tests use in-memory sqlite; run everything with `uv run pytest`.

---

### Task 1: Dependency + config

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/config.py`
- Test: `tests/test_config.py` (create)

- [ ] **Step 1: Add the anthropic dependency**

Run: `uv add anthropic`
Expected: `anthropic` appears under `[project].dependencies` in `pyproject.toml`; lockfile + venv updated.

- [ ] **Step 2: Write the failing test for config defaults**

Create `tests/test_config.py`:

```python
import importlib

import pytest


def test_models_have_defaults(monkeypatch):
    monkeypatch.delenv("ITINERARY_MODEL", raising=False)
    monkeypatch.delenv("DATE_MODEL", raising=False)
    import src.config as config
    importlib.reload(config)
    assert config.ITINERARY_MODEL == "claude-sonnet-4-6"
    assert config.DATE_MODEL == "claude-haiku-4-5-20251001"
    assert config.DEFAULT_SUNSET == "17:45"


def test_get_anthropic_key_raises_when_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import src.config as config
    importlib.reload(config)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        config.get_anthropic_key()
```

- [ ] **Step 3: Run the test, verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError: module 'src.config' has no attribute 'ITINERARY_MODEL'`.

- [ ] **Step 4: Implement config additions**

Append to `src/config.py` (after the existing `get_bot_token`):

```python
ITINERARY_MODEL = os.environ.get("ITINERARY_MODEL", "claude-sonnet-4-6")
DATE_MODEL = os.environ.get("DATE_MODEL", "claude-haiku-4-5-20251001")

# Hardcoded for Phase 2A: late-October sunset in Jeju (KST, HH:MM). Real
# per-location daylight lands in slice 2B (sunrise-sunset.org).
DEFAULT_SUNSET = "17:45"


def get_anthropic_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to your .env file."
        )
    return key
```

- [ ] **Step 5: Run the test, verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/config.py tests/test_config.py
git commit -m "feat: add anthropic dep + itinerary/date model config"
```

---

### Task 2: Database schema — trips + trip_members

**Files:**
- Modify: `src/db.py:10-26` (the `SCHEMA` string)
- Test: `tests/test_trips_repo.py` (create — schema test first)

- [ ] **Step 1: Write the failing schema test**

Create `tests/test_trips_repo.py`:

```python
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
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `uv run pytest tests/test_trips_repo.py -v`
Expected: FAIL — assertion error, `trips`/`trip_members` not in table set.

- [ ] **Step 3: Add the tables to `SCHEMA`**

In `src/db.py`, append the two tables inside the existing `SCHEMA` string (after the `answers` table, before the closing `"""`):

```sql
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
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `uv run pytest tests/test_trips_repo.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add src/db.py tests/test_trips_repo.py
git commit -m "feat: add trips + trip_members tables"
```

---

### Task 3: users repo — list quiz-completed users

**Files:**
- Modify: `src/repos/users.py`
- Test: `tests/test_trips_repo.py` (add test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_trips_repo.py`:

```python
from src.repos import users as users_repo


def test_list_completed_users_only_returns_finished(conn):
    users_repo.upsert_user(conn, 1, username="ken", first_name="Ken", now=NOW)
    users_repo.upsert_user(conn, 2, username="amy", first_name="Amy", now=NOW)
    users_repo.set_completed_at(conn, 1, when=NOW)  # only user 1 finished

    rows = users_repo.list_completed_users(conn)

    assert [r["telegram_user_id"] for r in rows] == [1]
    assert rows[0]["first_name"] == "Ken"
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `uv run pytest tests/test_trips_repo.py::test_list_completed_users_only_returns_finished -v`
Expected: FAIL — `AttributeError: module 'src.repos.users' has no attribute 'list_completed_users'`.

- [ ] **Step 3: Implement `list_completed_users`**

Append to `src/repos/users.py`:

```python
def list_completed_users(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """All users who have finished the quiz, ordered by name for stable display."""
    cur = conn.execute(
        "SELECT telegram_user_id, username, first_name FROM users "
        "WHERE completed_at IS NOT NULL "
        "ORDER BY first_name COLLATE NOCASE, telegram_user_id"
    )
    return cur.fetchall()
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `uv run pytest tests/test_trips_repo.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/repos/users.py tests/test_trips_repo.py
git commit -m "feat: list quiz-completed users"
```

---

### Task 4: trips repo

**Files:**
- Create: `src/repos/trips.py`
- Test: `tests/test_trips_repo.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_trips_repo.py`:

```python
from src.repos import trips as trips_repo


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

    ids_for_1 = {r["id"] for r in trips_repo.list_trips_for_user(conn, 1)}
    assert ids_for_1 == {t1}
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `uv run pytest tests/test_trips_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.repos.trips'`.

- [ ] **Step 3: Implement the trips repo**

Create `src/repos/trips.py`:

```python
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
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `uv run pytest tests/test_trips_repo.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/repos/trips.py tests/test_trips_repo.py
git commit -m "feat: trips repo (create, members, itinerary blob, list)"
```

---

### Task 5: profile summary (pure)

**Files:**
- Create: `src/profile/summary.py`
- Test: `tests/test_summary.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_summary.py`:

```python
from src.questions import Option, Question
from src.profile.summary import summarize_profile

QUESTIONS = [
    Question(
        id="food_adventure", category="Food", text="?", type="single",
        options=(Option("ramen", "🍜 Ramen"), Option("sushi", "🍣 Sushi")),
    ),
    Question(
        id="vibe_mix", category="Vibe", text="?", type="multi", select=2,
        options=(Option("nature", "🌿 Nature"), Option("food", "🍴 Food")),
    ),
    Question(
        id="dietary", category="Dietary", text="?", type="single",
        options=(Option("allergies", "⚠️ Allergies", "type them"),),
    ),
]


def test_summary_maps_ids_to_labels():
    answers = {"food_adventure": "ramen", "vibe_mix": '["nature", "food"]'}
    out = summarize_profile(QUESTIONS, answers)
    assert "Food: 🍜 Ramen" in out
    assert "Vibe: 🌿 Nature, 🍴 Food" in out


def test_summary_keeps_freetext_followup_value():
    answers = {"dietary": "peanuts, shellfish"}
    out = summarize_profile(QUESTIONS, answers)
    assert "Dietary: peanuts, shellfish" in out


def test_summary_skips_unanswered():
    out = summarize_profile(QUESTIONS, {"food_adventure": "sushi"})
    assert "Vibe" not in out
    assert "Dietary" not in out
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `uv run pytest tests/test_summary.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.profile.summary'`.

- [ ] **Step 3: Implement the summary (pure, plain text — no HTML)**

Create `src/profile/summary.py`:

```python
"""Pure: turn a user's saved answers into compact text for the LLM prompt."""

from __future__ import annotations

import json

from src.questions import Question


def _plain_value(question: Question, value: str) -> str:
    label_by_id = {o.id: o.label for o in question.options}
    if question.type == "multi":
        try:
            ids = json.loads(value)
        except json.JSONDecodeError:
            return value
        return ", ".join(label_by_id.get(i, i) for i in ids)
    # single: option id -> label, else a free-text followup value
    return label_by_id.get(value, value)


def summarize_profile(questions: list[Question], answers: dict[str, str]) -> str:
    """e.g. "Food: 🍜 Ramen; Vibe: 🌿 Nature, 🍴 Food". Skips unanswered."""
    parts = [
        f"{q.category}: {_plain_value(q, answers[q.id])}"
        for q in questions
        if q.id in answers
    ]
    return "; ".join(parts)
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `uv run pytest tests/test_summary.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/profile/summary.py tests/test_summary.py
git commit -m "feat: pure profile summary for prompt injection"
```

---

### Task 6: itinerary schema, dataclasses, tool definition, validation (pure)

**Files:**
- Create: `src/trip/__init__.py` (empty), `src/trip/schema.py`
- Test: `tests/test_itinerary_schema.py` (create)

- [ ] **Step 1: Create the package marker**

Create `src/trip/__init__.py` with a single line:

```python
"""Trip itinerary generation (Phase 2A)."""
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_itinerary_schema.py`:

```python
import pytest

from src.trip import schema

START, END = "2026-10-24", "2026-10-25"  # 2 days


def _good_raw():
    return {
        "trip_summary": "A balanced Jeju coastal ride.",
        "days": [
            {
                "day_number": 1, "date": "2026-10-24",
                "title": "West coast", "summary": "Easy start.",
                "stops": [
                    {"name": "Aewol", "type": "ride", "arrive": "09:00",
                     "depart": "10:30", "note": "Coffee with a view."},
                ],
                "daylight_note": "Finishes well before sunset.",
            },
            {
                "day_number": 2, "date": "2026-10-25",
                "title": "South coast", "summary": "Longer push.",
                "stops": [
                    {"name": "Jungmun", "type": "sight", "arrive": None,
                     "depart": None, "note": "Cliffs."},
                ],
                "daylight_note": "Tight; start early.",
            },
        ],
    }


def test_validate_accepts_good_itinerary():
    itin = schema.validate(_good_raw(), start_date=START, end_date=END)
    assert itin.trip_summary.startswith("A balanced")
    assert len(itin.days) == 2
    assert itin.days[0].stops[0].name == "Aewol"
    assert itin.days[1].stops[0].arrive is None


def test_validate_rejects_bad_stop_type():
    raw = _good_raw()
    raw["days"][0]["stops"][0]["type"] = "teleport"
    with pytest.raises(schema.ItineraryError, match="type"):
        schema.validate(raw, start_date=START, end_date=END)


def test_validate_rejects_wrong_day_count():
    raw = _good_raw()
    raw["days"].pop()  # only 1 day for a 2-day range
    with pytest.raises(schema.ItineraryError, match="day"):
        schema.validate(raw, start_date=START, end_date=END)


def test_validate_rejects_date_out_of_range():
    raw = _good_raw()
    raw["days"][1]["date"] = "2026-11-01"
    with pytest.raises(schema.ItineraryError, match="range"):
        schema.validate(raw, start_date=START, end_date=END)


def test_validate_rejects_missing_field():
    raw = _good_raw()
    del raw["days"][0]["title"]
    with pytest.raises(schema.ItineraryError):
        schema.validate(raw, start_date=START, end_date=END)


def test_from_dict_roundtrip():
    itin = schema.validate(_good_raw(), start_date=START, end_date=END)
    rebuilt = schema.Itinerary.from_dict(_good_raw())
    assert rebuilt.days[0].title == itin.days[0].title
```

- [ ] **Step 3: Run the tests, verify they fail**

Run: `uv run pytest tests/test_itinerary_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.trip.schema'`.

- [ ] **Step 4: Implement schema + validation**

Create `src/trip/schema.py`:

```python
"""Itinerary data model, the emit_itinerary tool contract, and validation (pure)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

ALLOWED_STOP_TYPES = frozenset(
    {"ride", "food", "sight", "rest", "accommodation"}
)


class ItineraryError(ValueError):
    """Raised when an itinerary payload fails validation."""


@dataclass(frozen=True)
class Stop:
    name: str
    type: str
    note: str
    arrive: str | None = None
    depart: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Stop":
        return cls(
            name=d["name"], type=d["type"], note=d["note"],
            arrive=d.get("arrive"), depart=d.get("depart"),
        )


@dataclass(frozen=True)
class Day:
    day_number: int
    date: str
    title: str
    summary: str
    daylight_note: str
    stops: tuple[Stop, ...]

    @classmethod
    def from_dict(cls, d: dict) -> "Day":
        return cls(
            day_number=d["day_number"], date=d["date"], title=d["title"],
            summary=d["summary"], daylight_note=d["daylight_note"],
            stops=tuple(Stop.from_dict(s) for s in d["stops"]),
        )


@dataclass(frozen=True)
class Itinerary:
    trip_summary: str
    days: tuple[Day, ...]

    @classmethod
    def from_dict(cls, d: dict) -> "Itinerary":
        return cls(
            trip_summary=d["trip_summary"],
            days=tuple(Day.from_dict(x) for x in d["days"]),
        )


# Tool contract for Anthropic structured output. The model is forced to call
# this tool, so its `input` arrives as a dict matching this schema.
EMIT_ITINERARY_TOOL = {
    "name": "emit_itinerary",
    "description": "Return the full multi-day trip itinerary as structured data.",
    "input_schema": {
        "type": "object",
        "properties": {
            "trip_summary": {
                "type": "string",
                "description": "1-2 sentences tuned to the group.",
            },
            "days": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "day_number": {"type": "integer"},
                        "date": {"type": "string", "description": "ISO YYYY-MM-DD"},
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                        "stops": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "type": {
                                        "type": "string",
                                        "enum": sorted(ALLOWED_STOP_TYPES),
                                    },
                                    "arrive": {
                                        "type": ["string", "null"],
                                        "description": "HH:MM local estimate",
                                    },
                                    "depart": {"type": ["string", "null"]},
                                    "note": {"type": "string"},
                                },
                                "required": ["name", "type", "note"],
                            },
                        },
                        "daylight_note": {"type": "string"},
                    },
                    "required": [
                        "day_number", "date", "title", "summary",
                        "stops", "daylight_note",
                    ],
                },
            },
        },
        "required": ["trip_summary", "days"],
    },
}

_REQUIRED_DAY_KEYS = ("day_number", "date", "title", "summary", "stops", "daylight_note")
_REQUIRED_STOP_KEYS = ("name", "type", "note")


def _expected_dates(start_date: str, end_date: str) -> list[str]:
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    span = (end - start).days
    return [(start.fromordinal(start.toordinal() + i)).isoformat() for i in range(span + 1)]


def validate(raw: dict, *, start_date: str, end_date: str) -> Itinerary:
    """Validate a raw emit_itinerary payload against the date range. Raises ItineraryError."""
    if not isinstance(raw, dict):
        raise ItineraryError("itinerary payload is not an object")
    if not isinstance(raw.get("trip_summary"), str) or not raw["trip_summary"]:
        raise ItineraryError("missing trip_summary")

    days = raw.get("days")
    if not isinstance(days, list) or not days:
        raise ItineraryError("missing non-empty days")

    expected = _expected_dates(start_date, end_date)
    if len(days) != len(expected):
        raise ItineraryError(
            f"expected {len(expected)} day(s) for the date range, got {len(days)}"
        )

    expected_set, seen = set(expected), set()
    for day in days:
        for key in _REQUIRED_DAY_KEYS:
            if key not in day:
                raise ItineraryError(f"day missing '{key}'")
        d = day["date"]
        if d not in expected_set:
            raise ItineraryError(f"day date {d!r} is outside the trip range")
        if d in seen:
            raise ItineraryError(f"duplicate day date {d!r}")
        seen.add(d)

        stops = day["stops"]
        if not isinstance(stops, list) or not stops:
            raise ItineraryError(f"day {d} has no stops")
        for stop in stops:
            for key in _REQUIRED_STOP_KEYS:
                if key not in stop:
                    raise ItineraryError(f"stop missing '{key}'")
            if stop["type"] not in ALLOWED_STOP_TYPES:
                raise ItineraryError(f"invalid stop type {stop['type']!r}")

    return Itinerary.from_dict(raw)
```

- [ ] **Step 5: Run the tests, verify they pass**

Run: `uv run pytest tests/test_itinerary_schema.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add src/trip/__init__.py src/trip/schema.py tests/test_itinerary_schema.py
git commit -m "feat: itinerary schema, tool contract, and validation"
```

---

### Task 7: prompt builder (pure)

**Files:**
- Create: `src/trip/prompt.py`
- Test: `tests/test_prompt.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_prompt.py`:

```python
from src.trip import prompt


def test_system_prompt_states_rules():
    sys = prompt.build_system_prompt()
    assert "emit_itinerary" in sys
    assert "every" in sys.lower()  # respect every member's profile
    assert "sunset" in sys.lower()


def test_user_prompt_includes_all_inputs():
    out = prompt.build_user_prompt(
        destination="Jeju",
        start_date="2026-10-24",
        end_date="2026-10-28",
        activity="cycling",
        sunset="17:45",
        member_summaries=["Ken: Food: Ramen", "Amy: Vibe: Nature"],
    )
    assert "Jeju" in out
    assert "2026-10-24" in out and "2026-10-28" in out
    assert "5" in out  # 5-day count
    assert "cycling" in out
    assert "17:45" in out
    assert "Ken: Food: Ramen" in out
    assert "Amy: Vibe: Nature" in out
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `uv run pytest tests/test_prompt.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.trip.prompt'`.

- [ ] **Step 3: Implement the prompt builder**

Create `src/trip/prompt.py`:

```python
"""Pure construction of the system + user prompts for itinerary generation."""

from __future__ import annotations

from datetime import date

ACTIVITY_LABELS = {
    "cycling": "a cycling trip",
    "self_drive": "a self-drive road trip",
    "general": "a general sightseeing trip",
}


def build_system_prompt() -> str:
    return (
        "You are a thoughtful travel companion planning a trip for a small group "
        "of friends who each filled out a preference quiz.\n\n"
        "Rules:\n"
        "- Respect EVERY member's profile. When preferences conflict (e.g. one "
        "night owl, two early birds; one vegetarian), explicitly negotiate a "
        "compromise and name it in the relevant day summary.\n"
        "- Plan at the stated activity's pace and aim to finish each day before "
        "the given sunset time; if a day is tight, say so in daylight_note.\n"
        "- Be specific and local. Name real places, dishes, and roads. Do NOT "
        "write generic filler like 'visit the famous local market'.\n"
        "- Arrival/departure times are your best estimates.\n"
        "- Return the plan ONLY by calling the emit_itinerary tool. Produce "
        "exactly one entry per day of the trip."
    )


def build_user_prompt(
    *,
    destination: str,
    start_date: str,
    end_date: str,
    activity: str,
    sunset: str,
    member_summaries: list[str],
) -> str:
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    day_count = (end - start).days + 1
    activity_label = ACTIVITY_LABELS.get(activity, activity)
    members = "\n".join(f"- {s}" for s in member_summaries)
    return (
        f"Plan {activity_label} to {destination}.\n"
        f"Dates: {start.isoformat()} ({start:%A}) to {end.isoformat()} "
        f"({end:%A}) — {day_count} day(s).\n"
        f"Local sunset is approximately {sunset}; daylight matters.\n\n"
        f"Party profiles:\n{members}\n\n"
        f"Build a day-by-day plan tuned to this specific group."
    )
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `uv run pytest tests/test_prompt.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/trip/prompt.py tests/test_prompt.py
git commit -m "feat: itinerary prompt builder"
```

---

### Task 8: rendering (pure, HTML-safe)

**Files:**
- Create: `src/trip/render.py`
- Test: `tests/test_trip_render.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_trip_render.py`:

```python
from src.trip import schema
from src.trip import render

START, END = "2026-10-24", "2026-10-24"  # 1 day


def _itin():
    raw = {
        "trip_summary": "Coastal & chill.",
        "days": [
            {
                "day_number": 1, "date": "2026-10-24",
                "title": "West coast", "summary": "Easy start.",
                "stops": [
                    {"name": "Aewol <Cafe>", "type": "food", "arrive": "09:00",
                     "depart": "10:30", "note": "Sea view."},
                    {"name": "Hallim", "type": "ride", "arrive": None,
                     "depart": None, "note": "Flat path."},
                ],
                "daylight_note": "Plenty of daylight.",
            },
        ],
    }
    return schema.validate(raw, start_date=START, end_date=END)


def test_render_itinerary_returns_lead_plus_one_per_day():
    msgs = render.render_itinerary(_itin(), member_names=["Ken", "Amy"])
    assert len(msgs) == 2  # lead + 1 day
    assert "Coastal &amp; chill." in msgs[0]  # summary HTML-escaped
    assert "Ken" in msgs[0] and "Amy" in msgs[0]
    assert "estimate" in msgs[0].lower()  # disclaimer present


def test_render_day_escapes_and_formats():
    day_msg = render.render_day(_itin().days[0])
    assert "Day 1" in day_msg
    assert "West coast" in day_msg
    assert "Aewol &lt;Cafe&gt;" in day_msg  # HTML-escaped stop name
    assert "09:00" in day_msg and "10:30" in day_msg
    assert "Plenty of daylight." in day_msg


def test_render_trips_list_marks_generated_state():
    rows = [
        {"id": 7, "destination": "Jeju", "start_date": "2026-10-24",
         "end_date": "2026-10-28", "itinerary_json": "{}"},
        {"id": 8, "destination": "Busan", "start_date": "2026-11-01",
         "end_date": "2026-11-03", "itinerary_json": None},
    ]
    out = render.render_trips_list(rows)
    assert "Jeju" in out and "Busan" in out
    assert "not generated" in out.lower()  # the NULL-itinerary trip
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `uv run pytest tests/test_trip_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.trip.render'`.

- [ ] **Step 3: Implement rendering**

Create `src/trip/render.py`:

```python
"""Pure rendering of itineraries and trip lists into Telegram HTML messages."""

from __future__ import annotations

from datetime import date
from html import escape

from src.trip.schema import Day, Itinerary

_TYPE_EMOJI = {
    "ride": "🚴",
    "food": "🍴",
    "sight": "📸",
    "rest": "☕",
    "accommodation": "🏨",
}

_DISCLAIMER = (
    "⏱ <i>Times are estimates for now — real cycling distances and daylight "
    "checks are coming in a later update.</i>"
)


def render_lead(itinerary: Itinerary, member_names: list[str]) -> str:
    names = ", ".join(escape(n) for n in member_names)
    return (
        f"<b>Your trip plan</b>\n{escape(itinerary.trip_summary)}\n\n"
        f"<b>Party:</b> {names}\n\n{_DISCLAIMER}"
    )


def _stop_line(stop) -> str:
    emoji = _TYPE_EMOJI.get(stop.type, "•")
    when = ""
    if stop.arrive or stop.depart:
        when = f" ({escape(stop.arrive or '?')}–{escape(stop.depart or '?')})"
    return f"{emoji} <b>{escape(stop.name)}</b>{when}\n   {escape(stop.note)}"


def render_day(day: Day) -> str:
    try:
        weekday = f", {date.fromisoformat(day.date):%a}"
    except ValueError:
        weekday = ""
    lines = [
        f"<b>Day {day.day_number} · {escape(day.date)}{weekday} · "
        f"{escape(day.title)}</b>",
        escape(day.summary),
        "",
    ]
    lines += [_stop_line(s) for s in day.stops]
    lines += ["", f"☀️ {escape(day.daylight_note)}"]
    return "\n".join(lines)


def render_itinerary(itinerary: Itinerary, member_names: list[str]) -> list[str]:
    """Lead message followed by one message per day."""
    return [render_lead(itinerary, member_names)] + [
        render_day(d) for d in itinerary.days
    ]


def render_trips_list(trips) -> str:
    if not trips:
        return "No trips yet — run /newtrip to plan one."
    lines = ["<b>Your trips</b>", ""]
    for t in trips:
        status = "" if t["itinerary_json"] else " — <i>not generated</i>"
        lines.append(
            f"#{t['id']} · {escape(t['destination'])} "
            f"({escape(t['start_date'])} → {escape(t['end_date'])}){status}"
        )
    return "\n".join(lines)
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `uv run pytest tests/test_trip_render.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/trip/render.py tests/test_trip_render.py
git commit -m "feat: itinerary + trips-list rendering"
```

---

### Task 9: Anthropic client factory (thin)

**Files:**
- Create: `src/llm/__init__.py` (empty), `src/llm/client.py`

No unit test — this is a thin wrapper that constructs the SDK object. It is exercised by the generator tests (via a fake) and manual smoke.

- [ ] **Step 1: Create the package marker**

Create `src/llm/__init__.py`:

```python
"""LLM client wiring."""
```

- [ ] **Step 2: Implement the client factory**

Create `src/llm/client.py`:

```python
"""Single place that constructs the Anthropic SDK client."""

from __future__ import annotations

import anthropic


def build_client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key)
```

- [ ] **Step 3: Verify it imports**

Run: `uv run python -c "from src.llm.client import build_client; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add src/llm/__init__.py src/llm/client.py
git commit -m "feat: anthropic client factory"
```

---

### Task 10: date parsing (dateutil) — pure, no network

**Decision change (2026-06-01):** date parsing no longer uses an LLM. Dates are a
structured field; `python-dateutil` + the wizard confirm-screen safety net is
simpler, deterministic, free, network-free, and fully unit-testable. This makes
`DATE_MODEL` (added in Task 1) dead config, so this task removes it.

**Files:**
- Modify: `pyproject.toml` (add `python-dateutil`)
- Modify: `src/config.py` + `tests/test_config.py` (remove dead `DATE_MODEL`)
- Create: `src/trip/dates.py`
- Test: `tests/test_dates.py` (create)

- [ ] **Step 1: Add the dateutil dependency**

Run: `uv add python-dateutil`
Expected: `python-dateutil` under `[project].dependencies`; lockfile updated.

- [ ] **Step 2: Remove the now-dead DATE_MODEL config**

In `src/config.py`, delete the line:
```python
DATE_MODEL = os.environ.get("DATE_MODEL", "claude-haiku-4-5-20251001")
```
In `tests/test_config.py`, inside `test_models_have_defaults`, delete the
`monkeypatch.delenv("DATE_MODEL", raising=False)` line and the
`assert config.DATE_MODEL == "claude-haiku-4-5-20251001"` line. Keep the
`ITINERARY_MODEL` and `DEFAULT_SUNSET` assertions (and the `ITINERARY_MODEL`
delenv).

- [ ] **Step 3: Write the failing tests**

Create `tests/test_dates.py`:

```python
from datetime import date

import pytest

from src.trip import dates

REF = date(2026, 6, 1)  # fixed "today" for determinism


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Oct 24-28", ("2026-10-24", "2026-10-28")),
        ("Oct 24 to 28", ("2026-10-24", "2026-10-28")),
        ("October 24 - 28", ("2026-10-24", "2026-10-28")),
        ("2026-10-24 to 2026-10-28", ("2026-10-24", "2026-10-28")),
        ("2026-10-24 - 2026-10-28", ("2026-10-24", "2026-10-28")),
    ],
)
def test_parse_common_range_forms(raw, expected):
    assert dates.parse_date_range(raw, reference=REF) == expected


def test_single_date_is_one_day_trip():
    assert dates.parse_date_range("2026-10-24", reference=REF) == (
        "2026-10-24",
        "2026-10-24",
    )


def test_bare_month_day_rolls_forward_when_in_the_past():
    # Reference is December; a bare "Oct 24-28" (no year) resolves to NEXT year.
    assert dates.parse_date_range("Oct 24-28", reference=date(2026, 12, 1)) == (
        "2027-10-24",
        "2027-10-28",
    )


def test_explicit_year_is_not_rolled_forward():
    # Explicit 2026 dates earlier than the reference stay in 2026 (year was given).
    assert dates.parse_date_range(
        "2026-01-10 to 2026-01-15", reference=date(2026, 6, 1)
    ) == ("2026-01-10", "2026-01-15")


def test_parse_rejects_gibberish():
    with pytest.raises(dates.DateParseError):
        dates.parse_date_range("sometime soon-ish", reference=REF)


def test_validate_rejects_reversed_range():
    with pytest.raises(dates.DateParseError, match="precede"):
        dates.validate_date_range("2026-10-28", "2026-10-24")


def test_validate_rejects_unparseable():
    with pytest.raises(dates.DateParseError):
        dates.validate_date_range("not-a-date", "2026-10-28")


def test_validate_rejects_overlong_span():
    with pytest.raises(dates.DateParseError, match="long"):
        dates.validate_date_range("2026-01-01", "2026-06-01")
```

- [ ] **Step 4: Run the tests, verify they fail**

Run: `uv run pytest tests/test_dates.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.trip.dates'`.

- [ ] **Step 5: Implement date parsing**

Create `src/trip/dates.py`:

```python
"""Parse a natural-language date range into ISO {start, end} using dateutil.

Pure + deterministic; no network. The wizard's confirm screen is the
user-facing safety net for the occasional misparse.

Supported forms (case-insensitive):
  "Oct 24-28", "Oct 24 to 28", "October 24 - 28",
  "2026-10-24 to 2026-10-28", "2026-10-24 - 2026-10-28", and a single date.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from dateutil import parser as dtparser

_MAX_SPAN_DAYS = 60

# Unambiguous range separators: word separators, an em/en dash or "..", or a
# hyphen WITH surrounding spaces. A bare hyphen is handled by _COMPACT below, so
# we never split the internal hyphens of an ISO date like 2026-10-24.
_RANGE_SEP = re.compile(
    r"\s+(?:to|until|through|thru)\s+|\s*(?:–|—|\.\.)\s*|\s+-\s+",
    re.IGNORECASE,
)
# Compact "<month words> DD-DD" (e.g. "Oct 24-28"): must start with a letter so a
# lone ISO date (which starts with a digit) is never mistaken for a range.
_COMPACT = re.compile(r"^([A-Za-z].*?\s+)(\d{1,2})\s*-\s*(\d{1,2})\s*$")


class DateParseError(ValueError):
    """Raised when a date range cannot be parsed or is invalid."""


def validate_date_range(start: str, end: str) -> None:
    try:
        s, e = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError as exc:
        raise DateParseError(f"unparseable date: {exc}") from exc
    if e < s:
        raise DateParseError("end date must not precede start date")
    if (e - s).days > _MAX_SPAN_DAYS:
        raise DateParseError("trip span looks too long (>60 days)")


def _split(text: str) -> tuple[str, str | None]:
    """Split a range string into (left, right); right is None for a single date."""
    parts = _RANGE_SEP.split(text, maxsplit=1)
    if len(parts) == 2 and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    m = _COMPACT.match(text)
    if m:
        return f"{m.group(1).strip()} {m.group(2)}", m.group(3)
    return text, None


def parse_date_range(raw_text: str, *, reference: date) -> tuple[str, str]:
    """Resolve raw_text into (start_iso, end_iso). Raises DateParseError."""
    text = raw_text.strip()
    if not text:
        raise DateParseError("no dates provided")
    left, right = _split(text)
    base = datetime(reference.year, reference.month, reference.day)
    try:
        start_dt = dtparser.parse(left, default=base, fuzzy=True)
        end_dt = (
            dtparser.parse(right, default=start_dt, fuzzy=True) if right else start_dt
        )
    except (ValueError, OverflowError) as exc:
        raise DateParseError(f"couldn't parse dates: {exc}") from exc
    start, end = start_dt.date(), end_dt.date()
    # If no explicit 4-digit year was given and the range is already past,
    # assume the next upcoming occurrence (e.g. "Oct 24-28" in December).
    year_given = re.search(r"\d{4}", text) is not None
    if not year_given and start < reference:
        try:
            start = start.replace(year=start.year + 1)
            end = end.replace(year=end.year + 1)
        except ValueError as exc:  # e.g. Feb 29 in a non-leap year
            raise DateParseError("ambiguous date; please include the year") from exc
    validate_date_range(start.isoformat(), end.isoformat())
    return start.isoformat(), end.isoformat()
```

- [ ] **Step 6: Run the tests, verify they pass**

Run: `uv run pytest tests/test_dates.py -v`
Expected: PASS (12 tests — 5 parametrized + 7).

- [ ] **Step 7: Run the full suite** (confirm the DATE_MODEL removal didn't break test_config)

Run: `uv run pytest`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock src/trip/dates.py tests/test_dates.py src/config.py tests/test_config.py
git commit -m "feat: dateutil natural-language date parsing (no LLM)"
```

---

### Task 11: itinerary generator (Sonnet) — with retry

**Files:**
- Create: `src/trip/generator.py`
- Test: `tests/test_generator.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_generator.py`:

```python
import pytest

from src.trip import generator, schema

START, END = "2026-10-24", "2026-10-24"  # 1 day


def _good_input():
    return {
        "trip_summary": "Nice.",
        "days": [
            {
                "day_number": 1, "date": "2026-10-24", "title": "A",
                "summary": "B", "daylight_note": "C",
                "stops": [{"name": "X", "type": "ride", "note": "Y"}],
            }
        ],
    }


def _bad_input():
    bad = _good_input()
    bad["days"][0]["stops"][0]["type"] = "nope"
    return bad


class _Block:
    def __init__(self, inp):
        self.type, self.name, self.input = "tool_use", "emit_itinerary", inp


class _Resp:
    def __init__(self, inp):
        self.content = [_Block(inp)]


class _SeqClient:
    """Returns a queued payload per create() call; records call count."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.calls = 0
        self.messages = self

    def create(self, **kwargs):
        self.calls += 1
        return _Resp(self._payloads.pop(0))


def test_generate_returns_validated_itinerary():
    client = _SeqClient([_good_input()])
    itin = generator.generate_itinerary(
        client, "sonnet", system="s", user="u", start_date=START, end_date=END
    )
    assert isinstance(itin, schema.Itinerary)
    assert client.calls == 1


def test_generate_retries_once_on_invalid_then_succeeds():
    client = _SeqClient([_bad_input(), _good_input()])
    itin = generator.generate_itinerary(
        client, "sonnet", system="s", user="u", start_date=START, end_date=END
    )
    assert isinstance(itin, schema.Itinerary)
    assert client.calls == 2


def test_generate_raises_after_retries_exhausted():
    client = _SeqClient([_bad_input(), _bad_input()])
    with pytest.raises(schema.ItineraryError):
        generator.generate_itinerary(
            client, "sonnet", system="s", user="u", start_date=START, end_date=END
        )
    assert client.calls == 2
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `uv run pytest tests/test_generator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.trip.generator'`.

- [ ] **Step 3: Implement the generator**

Create `src/trip/generator.py`:

```python
"""Call Claude Sonnet with the emit_itinerary tool and validate the result.

Network-touching but thin: prompt building, schema, and validation live
elsewhere and are unit-tested. Retry logic is covered with a fake client.
"""

from __future__ import annotations

from src.trip.schema import EMIT_ITINERARY_TOOL, Itinerary, ItineraryError, validate

_MAX_TOKENS = 4096


def _extract_itinerary_input(response) -> dict | None:
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "emit_itinerary":
            return block.input
    return None


def generate_itinerary(
    client,
    model: str,
    *,
    system: str,
    user: str,
    start_date: str,
    end_date: str,
    max_retries: int = 1,
) -> Itinerary:
    """Generate + validate an itinerary. Retries once on validation failure."""
    last_error: ItineraryError | None = None
    for attempt in range(max_retries + 1):
        response = client.messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            tools=[EMIT_ITINERARY_TOOL],
            tool_choice={"type": "tool", "name": "emit_itinerary"},
        )
        raw = _extract_itinerary_input(response)
        if raw is None:
            last_error = ItineraryError("model did not call emit_itinerary")
            continue
        try:
            return validate(raw, start_date=start_date, end_date=end_date)
        except ItineraryError as exc:
            last_error = exc
    raise last_error if last_error else ItineraryError("generation failed")
```

> Note: `system` is passed as a cache-control block per the `claude-api` skill's prompt-caching guidance. The fake client in tests ignores kwargs, so this is transparent to the unit tests.

- [ ] **Step 4: Run the tests, verify they pass**

Run: `uv run pytest tests/test_generator.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/trip/generator.py tests/test_generator.py
git commit -m "feat: Sonnet itinerary generator with validate-and-retry"
```

---

### Task 12: wizard pure logic + FSM states + session helpers

**Files:**
- Create: `src/trip/states.py`, `src/trip/session.py`, `src/trip/wizard.py`
- Test: `tests/test_wizard.py` (create)

- [ ] **Step 1: Write the failing tests (pure wizard helpers)**

Create `tests/test_wizard.py`:

```python
from src.trip import wizard


def test_activity_options_are_three_known_ids():
    ids = {oid for _label, oid in wizard.ACTIVITY_OPTIONS}
    assert ids == {"cycling", "self_drive", "general"}


def test_toggle_member_adds_and_removes_but_locks_creator():
    current = [1]  # creator
    assert wizard.toggle_member(current, 2, locked=1) == [1, 2]
    assert wizard.toggle_member([1, 2], 2, locked=1) == [1]
    # creator can never be removed
    assert wizard.toggle_member([1, 2], 1, locked=1) == [1, 2]


def test_member_keyboard_marks_selected_and_locks_creator():
    users = [
        {"telegram_user_id": 1, "first_name": "Ken", "username": "k"},
        {"telegram_user_id": 2, "first_name": "Amy", "username": "a"},
    ]
    rows = wizard.member_keyboard(users, selected=[1], locked=1)
    flat = {data: label for row in rows for label, data in row}
    # creator row shows a lock; selected shows a check; Done row present
    assert any("🔒" in label for label in flat.values())
    assert any(data == "memdone" for row in rows for _l, data in row)
    assert "mem:2" in flat


def test_day_count_inclusive():
    assert wizard.day_count("2026-10-24", "2026-10-28") == 5


def test_confirm_summary_contains_inputs():
    out = wizard.confirm_summary(
        destination="Jeju", start_date="2026-10-24", end_date="2026-10-28",
        activity="cycling", member_names=["Ken", "Amy"],
    )
    assert "Jeju" in out and "cycling" in out
    assert "Ken" in out and "Amy" in out
    assert "5" in out
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `uv run pytest tests/test_wizard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.trip.wizard'`.

- [ ] **Step 3: Implement states, session, and wizard helpers**

Create `src/trip/states.py`:

```python
"""aiogram FSM states for the /newtrip wizard."""

from aiogram.fsm.state import State, StatesGroup


class NewTrip(StatesGroup):
    destination = State()
    dates = State()
    activity = State()
    party = State()
    confirm = State()
```

Create `src/trip/session.py`:

```python
"""Helpers over aiogram FSMContext for /newtrip wizard data.

FSM data keys: destination, start_date, end_date, activity, member_ids (list[int]).
"""

from __future__ import annotations

from aiogram.fsm.context import FSMContext


async def set_field(state: FSMContext, **fields) -> None:
    await state.update_data(**fields)


async def get_field(state: FSMContext, key: str, default=None):
    return (await state.get_data()).get(key, default)


async def get_member_ids(state: FSMContext) -> list[int]:
    return list((await state.get_data()).get("member_ids", []))


async def set_member_ids(state: FSMContext, ids: list[int]) -> None:
    await state.update_data(member_ids=ids)
```

Create `src/trip/wizard.py`:

```python
"""Pure helpers for the /newtrip wizard: options, member toggle, keyboards, summary."""

from __future__ import annotations

from datetime import date

ACTIVITY_OPTIONS: list[tuple[str, str]] = [
    ("🚲 Cycling", "cycling"),
    ("🚗 Self-drive", "self_drive"),
    ("🧭 General", "general"),
]
_ACTIVITY_LABEL = {oid: label for label, oid in ACTIVITY_OPTIONS}


def day_count(start_date: str, end_date: str) -> int:
    s, e = date.fromisoformat(start_date), date.fromisoformat(end_date)
    return (e - s).days + 1


def activity_keyboard() -> list[list[tuple[str, str]]]:
    return [[(label, f"act:{oid}")] for label, oid in ACTIVITY_OPTIONS]


def toggle_member(current: list[int], uid: int, *, locked: int) -> list[int]:
    """Toggle uid in the selection. The locked (creator) id can never be removed."""
    if uid == locked:
        return current if locked in current else [*current, locked]
    if uid in current:
        return [x for x in current if x != uid]
    return [*current, uid]


def _display_name(user: dict) -> str:
    return user["first_name"] or (f"@{user['username']}" if user["username"] else "Traveler")


def member_keyboard(users, selected: list[int], locked: int) -> list[list[tuple[str, str]]]:
    """One toggle row per user (creator locked + always checked), then a Done row."""
    rows: list[list[tuple[str, str]]] = []
    for u in users:
        uid = u["telegram_user_id"]
        name = _display_name(u)
        if uid == locked:
            label = f"🔒 {name} (you)"
        elif uid in selected:
            label = f"✅ {name}"
        else:
            label = name
        rows.append([(label, f"mem:{uid}")])
    rows.append([(f"✔️ Done ({len(selected)})", "memdone")])
    return rows


def confirm_summary(
    *,
    destination: str,
    start_date: str,
    end_date: str,
    activity: str,
    member_names: list[str],
) -> str:
    names = ", ".join(member_names)
    return (
        "<b>Ready to plan?</b>\n"
        f"📍 <b>Destination:</b> {destination}\n"
        f"📅 <b>Dates:</b> {start_date} → {end_date} "
        f"({day_count(start_date, end_date)} days)\n"
        f"🏃 <b>Activity:</b> {_ACTIVITY_LABEL.get(activity, activity)}\n"
        f"👥 <b>Party:</b> {names}"
    )
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `uv run pytest tests/test_wizard.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/trip/states.py src/trip/session.py src/trip/wizard.py tests/test_wizard.py
git commit -m "feat: newtrip wizard states, session, and pure helpers"
```

---

### Task 13: trip handlers + bot wiring + /help update

**Files:**
- Create: `src/trip/handlers.py`
- Modify: `src/bot.py`
- Modify: `src/quiz/handlers.py:101-108` (`cmd_help`)

Telegram glue, no live-bot unit tests (matches Phase 1). Verified by import + the manual smoke checklist in Task 14.

- [ ] **Step 1: Implement the trip handlers**

Create `src/trip/handlers.py`:

```python
"""aiogram Router: the /newtrip wizard, /trips, and view/retry callbacks."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timezone

import anthropic
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.config import DEFAULT_SUNSET, ITINERARY_MODEL
from src.profile.summary import summarize_profile
from src.questions import Question
from src.trip import dates, generator, prompt, render, session, wizard
from src.trip.schema import Itinerary, ItineraryError
from src.trip.states import NewTrip
from src.repos import answers as answers_repo
from src.repos import trips as trips_repo
from src.repos import users as users_repo

logger = logging.getLogger(__name__)
router = Router()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _markup(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=data) for label, data in row]
            for row in rows
        ]
    )


def _display_name(row) -> str:
    return row["first_name"] or (f"@{row['username']}" if row["username"] else "Traveler")


# ---- /newtrip wizard --------------------------------------------------------

@router.message(Command("newtrip"))
async def cmd_newtrip(message: Message, state: FSMContext, conn: sqlite3.Connection) -> None:
    user = users_repo.get_user(conn, message.from_user.id)
    if user is None or user["completed_at"] is None:
        await message.answer("Finish your profile first — run /start, then /newtrip.")
        return
    await state.clear()
    await state.set_state(NewTrip.destination)
    await message.answer("✈️ New trip! Where are we going?")


@router.message(NewTrip.destination, F.text)
async def on_destination(message: Message, state: FSMContext) -> None:
    await session.set_field(state, destination=message.text.strip())
    await state.set_state(NewTrip.dates)
    await message.answer("📅 When? e.g. \"Oct 24-28\" or \"24 to 28 October\".")


@router.message(NewTrip.dates, F.text)
async def on_dates(message: Message, state: FSMContext) -> None:
    today = datetime.now(timezone.utc).date()
    try:
        # dateutil parsing is fast + synchronous — no thread offload needed.
        start, end = dates.parse_date_range(message.text.strip(), reference=today)
    except dates.DateParseError:
        await message.answer("Couldn't read those dates — try \"Oct 24-28\".")
        return
    await session.set_field(state, start_date=start, end_date=end)
    await state.set_state(NewTrip.activity)
    await message.answer(
        f"Got it: {start} → {end}. What kind of trip?",
        reply_markup=_markup(wizard.activity_keyboard()),
    )


@router.callback_query(NewTrip.activity, F.data.startswith("act:"))
async def on_activity(
    cb: CallbackQuery, state: FSMContext, conn: sqlite3.Connection
) -> None:
    activity = cb.data.split(":", 1)[1]
    await session.set_field(state, activity=activity)
    creator_id = cb.from_user.id
    await session.set_member_ids(state, [creator_id])
    await state.set_state(NewTrip.party)
    users = users_repo.list_completed_users(conn)
    await cb.message.answer(
        "👥 Who's coming? Tap to add, then Done.",
        reply_markup=_markup(wizard.member_keyboard(users, [creator_id], creator_id)),
    )
    await cb.answer()


@router.callback_query(NewTrip.party, F.data.startswith("mem:"))
async def on_member_toggle(
    cb: CallbackQuery, state: FSMContext, conn: sqlite3.Connection
) -> None:
    uid = int(cb.data.split(":", 1)[1])
    creator_id = cb.from_user.id
    current = await session.get_member_ids(state)
    updated = wizard.toggle_member(current, uid, locked=creator_id)
    if updated != current:
        await session.set_member_ids(state, updated)
        users = users_repo.list_completed_users(conn)
        await cb.message.edit_reply_markup(
            reply_markup=_markup(wizard.member_keyboard(users, updated, creator_id))
        )
    await cb.answer()


@router.callback_query(NewTrip.party, F.data == "memdone")
async def on_party_done(
    cb: CallbackQuery, state: FSMContext, conn: sqlite3.Connection
) -> None:
    member_ids = await session.get_member_ids(state)
    data = await state.get_data()
    names = [_display_name(users_repo.get_user(conn, uid)) for uid in member_ids]
    summary = wizard.confirm_summary(
        destination=data["destination"], start_date=data["start_date"],
        end_date=data["end_date"], activity=data["activity"], member_names=names,
    )
    await state.set_state(NewTrip.confirm)
    await cb.message.answer(
        summary,
        parse_mode="HTML",
        reply_markup=_markup([[("✨ Generate", "gen"), ("↩️ Start over", "restart")]]),
    )
    await cb.answer()


@router.callback_query(NewTrip.confirm, F.data == "restart")
async def on_restart(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(NewTrip.destination)
    await cb.message.answer("Okay, starting over. Where are we going?")
    await cb.answer()


@router.callback_query(NewTrip.confirm, F.data == "gen")
async def on_generate(
    cb: CallbackQuery,
    state: FSMContext,
    conn: sqlite3.Connection,
    questions: list[Question],
    anthro: anthropic.Anthropic,
) -> None:
    data = await state.get_data()
    member_ids = await session.get_member_ids(state)
    await cb.answer()
    await state.clear()

    trip_id = trips_repo.create_trip(
        conn, creator_id=cb.from_user.id, destination=data["destination"],
        start_date=data["start_date"], end_date=data["end_date"],
        activity=data["activity"], now=_now(),
    )
    for uid in member_ids:
        trips_repo.add_member(conn, trip_id, uid)

    await cb.message.answer("✍️ Planning your trip… (~20s)")
    await _generate_and_send(cb.message, conn, questions, anthro, trip_id)


@router.message(NewTrip.dates)
@router.message(NewTrip.destination)
async def wizard_expects_text(message: Message) -> None:
    await message.answer("Type your answer as text, please.")


# ---- /trips + view/retry ----------------------------------------------------

@router.message(Command("trips"))
async def cmd_trips(message: Message, conn: sqlite3.Connection) -> None:
    rows = trips_repo.list_trips_for_user(conn, message.from_user.id)
    kb = [[(f"View #{r['id']} · {r['destination']}", f"view:{r['id']}")] for r in rows]
    await message.answer(
        render.render_trips_list(rows),
        parse_mode="HTML",
        reply_markup=_markup(kb) if kb else None,
    )


@router.callback_query(F.data.startswith("view:"))
async def on_view_trip(
    cb: CallbackQuery, conn: sqlite3.Connection
) -> None:
    trip_id = int(cb.data.split(":", 1)[1])
    trip = trips_repo.get_trip(conn, trip_id)
    if trip is None:
        await cb.answer("That trip is gone.")
        return
    if not trip["itinerary_json"]:
        await cb.message.answer(
            "That trip isn't generated yet.",
            reply_markup=_markup([[("🔁 Generate now", f"retry:{trip_id}")]]),
        )
        await cb.answer()
        return
    itin = Itinerary.from_dict(json.loads(trip["itinerary_json"]))
    names = _member_names(conn, trip_id)
    for msg in render.render_itinerary(itin, names):
        await cb.message.answer(msg, parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("retry:"))
async def on_retry_trip(
    cb: CallbackQuery,
    conn: sqlite3.Connection,
    questions: list[Question],
    anthro: anthropic.Anthropic,
) -> None:
    trip_id = int(cb.data.split(":", 1)[1])
    await cb.answer()
    await cb.message.answer("✍️ Planning your trip… (~20s)")
    await _generate_and_send(cb.message, conn, questions, anthro, trip_id)


@router.callback_query()
async def stale_trip_callback(cb: CallbackQuery) -> None:
    await cb.answer("That button's no longer active — /trips or /newtrip.")


# ---- shared generation path -------------------------------------------------

def _member_names(conn: sqlite3.Connection, trip_id: int) -> list[str]:
    return [_display_name(users_repo.get_user(conn, uid))
            for uid in trips_repo.get_members(conn, trip_id)]


def _generate_blocking(
    conn: sqlite3.Connection,
    questions: list[Question],
    anthro: anthropic.Anthropic,
    trip: sqlite3.Row,
    member_ids: list[int],
) -> Itinerary:
    summaries = []
    for uid in member_ids:
        row = users_repo.get_user(conn, uid)
        answers = answers_repo.get_answers(conn, uid)
        summaries.append(f"{_display_name(row)}: {summarize_profile(questions, answers)}")
    user_prompt = prompt.build_user_prompt(
        destination=trip["destination"], start_date=trip["start_date"],
        end_date=trip["end_date"], activity=trip["activity"],
        sunset=DEFAULT_SUNSET, member_summaries=summaries,
    )
    return generator.generate_itinerary(
        anthro, ITINERARY_MODEL,
        system=prompt.build_system_prompt(), user=user_prompt,
        start_date=trip["start_date"], end_date=trip["end_date"],
    )


async def _generate_and_send(
    target: Message,
    conn: sqlite3.Connection,
    questions: list[Question],
    anthro: anthropic.Anthropic,
    trip_id: int,
) -> None:
    trip = trips_repo.get_trip(conn, trip_id)
    member_ids = trips_repo.get_members(conn, trip_id)
    try:
        itin = await asyncio.to_thread(
            _generate_blocking, conn, questions, anthro, trip, member_ids
        )
    except (ItineraryError, anthropic.AnthropicError) as exc:
        logger.warning("itinerary generation failed for trip %s: %s", trip_id, exc)
        await target.answer(
            "😕 Couldn't plan that right now. Try again from /trips."
        )
        return
    trips_repo.save_itinerary(
        conn, trip_id, json.dumps(itin_to_dict(itin), ensure_ascii=False)
    )
    names = _member_names(conn, trip_id)
    for msg in render.render_itinerary(itin, names):
        await target.answer(msg, parse_mode="HTML")


def itin_to_dict(itin: Itinerary) -> dict:
    return {
        "trip_summary": itin.trip_summary,
        "days": [
            {
                "day_number": d.day_number, "date": d.date, "title": d.title,
                "summary": d.summary, "daylight_note": d.daylight_note,
                "stops": [
                    {"name": s.name, "type": s.type, "arrive": s.arrive,
                     "depart": s.depart, "note": s.note}
                    for s in d.stops
                ],
            }
            for d in itin.days
        ],
    }
```

> Note on storage: the validated `Itinerary` is serialized back to a dict via `itin_to_dict` so the stored blob matches the schema `from_dict` expects on read. (SQLite writes from the worker thread are fine here — one bot process, low volume.)

- [ ] **Step 2: Verify the handlers import**

Run: `uv run python -c "from src.trip.handlers import router; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Update `/help` text**

In `src/quiz/handlers.py`, replace the `cmd_help` body (around lines 101-108) with:

```python
@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "I'm your travel companion (in training).\n"
        "/start — take the onboarding quiz\n"
        "/restart — redo the quiz\n"
        "/profile — see your saved profile\n"
        "/newtrip — plan a new trip\n"
        "/trips — view your planned trips"
    )
```

- [ ] **Step 4: Wire the router + Anthropic client into `bot.py`**

Replace `src/bot.py` with:

```python
"""Entrypoint: build the bot, load data, start long-polling."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from src.config import QUESTIONS_PATH, get_anthropic_key, get_bot_token
from src.db import connect
from src.llm.client import build_client
from src.questions import load_questions
from src.quiz.handlers import router as quiz_router
from src.trip.handlers import router as trip_router

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    token = get_bot_token()
    anthro = build_client(get_anthropic_key())  # fail fast if key missing
    questions = load_questions(QUESTIONS_PATH)
    conn = connect()

    bot = Bot(token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(quiz_router)
    dp.include_router(trip_router)

    logging.info("Loaded %d questions. Starting long-polling…", len(questions))
    try:
        await dp.start_polling(bot, conn=conn, questions=questions, anthro=anthro)
    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
```

> Router order: `quiz_router` is included first and owns the `Quiz.*` states; `trip_router` owns the `NewTrip.*` states and the trip callbacks. The catch-all `stale_trip_callback` lives on `trip_router` and only fires for callbacks no handler above claimed. The quiz router's own `stale_callback`/`fallback` only match its states + unmatched messages; verify in smoke that `/newtrip` and quiz flows don't shadow each other.

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest -v`
Expected: PASS — all Phase 1 tests plus the new suites (`test_config`, `test_trips_repo`, `test_summary`, `test_itinerary_schema`, `test_prompt`, `test_trip_render`, `test_dates`, `test_generator`, `test_wizard`).

- [ ] **Step 6: Commit**

```bash
git add src/trip/handlers.py src/bot.py src/quiz/handlers.py
git commit -m "feat: /newtrip wizard + /trips handlers, wired into bot"
```

---

### Task 14: docs + manual smoke verification

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Add the key to `.env.example`**

Append to `.env.example`:

```
ANTHROPIC_API_KEY=
# Optional override:
# ITINERARY_MODEL=claude-sonnet-4-6
```

- [ ] **Step 2: Document setup in `README.md`**

Add an "Itinerary generation (Phase 2A)" section to `README.md` covering:
- Get an Anthropic API key from console.anthropic.com and set `ANTHROPIC_API_KEY` in `.env`.
- `/newtrip` runs in DM: destination → dates (natural language) → activity → pick party (quiz-completed users) → Generate.
- `/trips` lists trips; tap to re-view or to generate a not-yet-generated trip.
- Note: distances/times are LLM estimates in 2A; real routing + daylight land in 2B.

- [ ] **Step 3: Manual smoke test (requires `BOT_TOKEN` + `ANTHROPIC_API_KEY`)**

Run: `uv run python -m src.bot`

In Telegram DM with the bot, verify:
1. Two accounts each `/start` → finish the quiz (so ≥2 completed profiles exist).
2. `/newtrip` → enter "Jeju" → "Oct 24-28" → tap 🚲 Cycling → toggle the other member on → Done → confirm screen shows Jeju, 2026 dates, 5 days, both names.
3. Tap ✨ Generate → "planning…" appears → a lead message + 5 day messages arrive, HTML renders cleanly, days reference the members' actual preferences.
4. `/trips` → lists the trip → tapping it re-renders the saved itinerary.
5. Restart the bot process → `/trips` → trip still there and viewable (persistence).
6. `/newtrip` with a user who never finished the quiz → blocked with the "finish your profile first" message.
7. Tap a stale button from an old message → friendly toast, no hung spinner.

Expected: all seven behave as described.

- [ ] **Step 4: Commit**

```bash
git add .env.example README.md
git commit -m "docs: Phase 2A setup + smoke checklist"
```

---

## Self-Review

**Spec coverage:**
- `/newtrip` wizard (destination/dates/activity/party) → Tasks 12-13. ✓
- Party assembly via DM pick from quiz-completed users → Tasks 3, 12, 13. ✓
- Build prompt from all profiles + sunset + dates/activity → Tasks 5, 7, 13. ✓
- Sonnet structured JSON via forced tool call → Tasks 6, 11. ✓
- JSON-blob storage on trips row → Tasks 2, 4, 13. ✓
- Per-day text rendering + lead disclaimer → Task 8. ✓
- `/trips` list + view + retry-on-NULL → Tasks 4, 13. ✓
- Natural-language dates via dateutil (no LLM) + confirm safety net → Tasks 10, 12-13. ✓
- Hardcoded sunset + model self-flags daylight → Tasks 1, 7 (prompt rule), 8 (footer). ✓
- Error handling: missing key fail-fast (Task 1/13 wiring), no-profile block (13), LLM failure retryable (11, 13), stale callbacks (13). ✓
- Sonnet default + Haiku A/B note → config defaults (Task 1); A/B is a soak action, not code. ✓
- Out of scope (maps, daylight API, Mini App, edit-by-chat) → not implemented. ✓

**Placeholder scan:** README Task 14 Step 2 describes section contents rather than pasting final prose — acceptable (copy is the wife's surface per the spec) but every other step has complete code/commands. No TBDs in code.

**Type consistency:** `Itinerary`/`Day`/`Stop` (frozen dataclasses, `from_dict`) used identically across schema (Task 6), render (Task 8), generator (Task 11), handlers (Task 13). `validate(raw, *, start_date, end_date)` signature consistent. `generate_itinerary(client, model, *, system, user, start_date, end_date)` consistent between test and handler. `member_keyboard(users, selected, locked)` / `toggle_member(current, uid, *, locked)` consistent between wizard tests and handlers. Storage round-trip: `itin_to_dict` (handlers) produces the dict shape `Itinerary.from_dict` (schema) reads. ✓

**Coupling:** `_generate_blocking` uses `answers_repo.get_answers(conn, uid)` (not an inline SQL query) so all answer reads go through the repo. ✓
