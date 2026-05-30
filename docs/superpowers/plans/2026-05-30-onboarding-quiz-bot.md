# Onboarding Quiz Bot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Telegram bot that runs a ~10-question multiple-choice onboarding quiz in DMs, stores answers per user in SQLite, and shows them back via `/profile`.

**Architecture:** Pure logic (question loading/validation, quiz engine, profile rendering, repositories) is separated from Telegram wiring so it is unit-testable without a live bot. aiogram 3.x handles updates via long-polling; an in-memory FSM tracks per-user quiz progress while completed answers persist in SQLite. Quiz content lives in a git-tracked `questions.json` (the wife's editing surface). No LLM in Phase 1.

**Tech Stack:** Python 3.11+, aiogram 3.x, python-dotenv, stdlib `sqlite3`/`json`, pytest.

**Source spec:** `docs/superpowers/specs/2026-05-30-onboarding-quiz-bot-design.md`

---

## File Structure

```
pyproject.toml            # project metadata + deps + pytest config
.gitignore                # .env, *.db, __pycache__, .pytest_cache
.env.example              # BOT_TOKEN=
README.md                 # BotFather setup + run instructions
src/
  __init__.py
  config.py               # env loading (BOT_TOKEN), file paths
  questions.py            # Option/Question dataclasses, load + validate questions.json
  questions.json          # quiz content (wife edits this)
  db.py                   # sqlite connection + idempotent schema init
  repos/
    __init__.py
    users.py              # upsert user, get user, set completed_at
    answers.py            # upsert answer, get answers map, clear user answers
  quiz/
    __init__.py
    engine.py             # PURE: next question, toggle select-N, selection-complete, followup lookup
    states.py             # aiogram FSM StatesGroup
    session.py            # FSMContext data helpers (selections, followup qid)
    handlers.py           # Router: /start /restart /profile /help, callbacks, followup text
  profile/
    __init__.py
    render.py             # PURE: format answers + questions -> profile message text
  bot.py                  # entry: load env, build Bot+Dispatcher, include router, start_polling
tests/
  __init__.py
  conftest.py             # shared fixtures (sample questions, in-memory db)
  fixtures/
    valid_questions.json
    invalid_dup_ids.json
  test_questions.py
  test_engine.py
  test_render.py
  test_repos.py
```

**Data shapes (consistent across all tasks):**

- `Option`: frozen dataclass `(id: str, label: str, followup: str | None = None)`
- `Question`: frozen dataclass `(id: str, category: str, text: str, type: str, options: tuple[Option, ...], select: int | None = None)`
- Stored answer **value** (TEXT in DB):
  - `single` question → the chosen option `id` (e.g. `"ramen"`)
  - `multi` question → JSON array of option ids (e.g. `'["nature","food"]'`)
  - a `single` option that carries a `followup` → the user's free text replaces the value (e.g. `"peanuts, shellfish"`)
- "answers map" = `dict[str, str]` mapping `question_id -> value`.

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `src/__init__.py`, `src/repos/__init__.py`, `src/quiz/__init__.py`, `src/profile/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "travel-companion-bot"
version = "0.1.0"
description = "Telegram travel companion bot — Phase 1 onboarding quiz"
requires-python = ">=3.11"
dependencies = [
    "aiogram>=3.4,<4",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.setuptools.packages.find]
where = ["."]
include = ["src*"]
```

- [ ] **Step 2: Create `.gitignore`**

```gitignore
.env
*.db
__pycache__/
*.pyc
.pytest_cache/
.venv/
venv/
*.egg-info/
```

- [ ] **Step 3: Create `.env.example`**

```dotenv
# Telegram bot token from BotFather (/newbot). Do NOT commit the real .env.
BOT_TOKEN=
```

- [ ] **Step 4: Create empty package markers**

Create these files, each empty:
`src/__init__.py`, `src/repos/__init__.py`, `src/quiz/__init__.py`, `src/profile/__init__.py`, `tests/__init__.py`

- [ ] **Step 5: Create and activate a virtualenv, install deps**

Run (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```
Expected: aiogram, python-dotenv, pytest, pytest-asyncio install without error.

- [ ] **Step 6: Verify pytest runs (no tests yet)**

Run: `pytest`
Expected: exits 0 (or "no tests ran") — confirms config is valid.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore .env.example src tests
git commit -m "chore: scaffold Python project for onboarding quiz bot

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Question config + validation

**Files:**
- Create: `src/questions.py`
- Create: `src/questions.json`
- Create: `tests/fixtures/valid_questions.json`
- Create: `tests/fixtures/invalid_dup_ids.json`
- Test: `tests/test_questions.py`

- [ ] **Step 1: Create test fixtures**

`tests/fixtures/valid_questions.json`:
```json
[
  {
    "id": "food_adventure",
    "category": "Food adventurousness",
    "type": "single",
    "text": "Your last meal on earth would be?",
    "options": [
      {"id": "ramen", "label": "🍜 Ramen"},
      {"id": "sushi", "label": "🍣 Sushi"}
    ]
  },
  {
    "id": "dietary",
    "category": "Dietary needs",
    "type": "single",
    "text": "Anything we should know about food?",
    "options": [
      {"id": "none", "label": "No restrictions"},
      {"id": "allergies", "label": "Allergies", "followup": "Type your allergies, separated by commas:"}
    ]
  },
  {
    "id": "vibe_mix",
    "category": "Vibe mix",
    "type": "multi",
    "select": 2,
    "text": "Pick your top 2 trip vibes:",
    "options": [
      {"id": "nature", "label": "🌿 Nature"},
      {"id": "culture", "label": "🏛 Culture"},
      {"id": "food", "label": "🍴 Food"}
    ]
  }
]
```

`tests/fixtures/invalid_dup_ids.json`:
```json
[
  {"id": "dup", "category": "A", "type": "single", "text": "Q1?",
   "options": [{"id": "x", "label": "X"}]},
  {"id": "dup", "category": "B", "type": "single", "text": "Q2?",
   "options": [{"id": "y", "label": "Y"}]}
]
```

- [ ] **Step 2: Write the failing tests**

`tests/test_questions.py`:
```python
from pathlib import Path

import pytest

from src.questions import (
    Option,
    Question,
    QuestionConfigError,
    load_questions,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_valid_returns_questions_in_order():
    questions = load_questions(FIXTURES / "valid_questions.json")
    assert [q.id for q in questions] == ["food_adventure", "dietary", "vibe_mix"]
    assert isinstance(questions[0], Question)
    assert isinstance(questions[0].options[0], Option)


def test_single_question_parsed():
    q = load_questions(FIXTURES / "valid_questions.json")[0]
    assert q.type == "single"
    assert q.select is None
    assert q.options[0].id == "ramen"
    assert q.options[0].label == "🍜 Ramen"
    assert q.options[0].followup is None


def test_followup_option_parsed():
    dietary = load_questions(FIXTURES / "valid_questions.json")[1]
    allergies = dietary.options[1]
    assert allergies.id == "allergies"
    assert allergies.followup == "Type your allergies, separated by commas:"


def test_multi_question_parsed():
    vibe = load_questions(FIXTURES / "valid_questions.json")[2]
    assert vibe.type == "multi"
    assert vibe.select == 2
    assert len(vibe.options) == 3


def test_duplicate_question_ids_rejected():
    with pytest.raises(QuestionConfigError, match="duplicate question id"):
        load_questions(FIXTURES / "invalid_dup_ids.json")


def test_empty_array_rejected(tmp_path):
    p = tmp_path / "empty.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(QuestionConfigError, match="at least one question"):
        load_questions(p)


def test_multi_without_valid_select_rejected(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(
        '[{"id":"q","category":"C","type":"multi","text":"?",'
        '"options":[{"id":"a","label":"A"}],"select":2}]',
        encoding="utf-8",
    )
    with pytest.raises(QuestionConfigError, match="select"):
        load_questions(p)


def test_real_questions_json_is_valid():
    # The shipped content file must always load.
    questions = load_questions(Path("src/questions.json"))
    assert len(questions) == 10
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_questions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.questions'` (and the last test fails until `src/questions.json` exists with 10 questions).

- [ ] **Step 4: Implement `src/questions.py`**

```python
"""Load and validate the quiz question config (questions.json)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class QuestionConfigError(ValueError):
    """Raised when questions.json is malformed."""


@dataclass(frozen=True)
class Option:
    id: str
    label: str
    followup: str | None = None


@dataclass(frozen=True)
class Question:
    id: str
    category: str
    text: str
    type: str
    options: tuple[Option, ...]
    select: int | None = None


def _parse_option(raw: dict, qid: str) -> Option:
    for key in ("id", "label"):
        if not isinstance(raw.get(key), str) or not raw[key]:
            raise QuestionConfigError(f"question '{qid}': option missing '{key}'")
    followup = raw.get("followup")
    if followup is not None and (not isinstance(followup, str) or not followup):
        raise QuestionConfigError(f"question '{qid}': option '{raw['id']}' has empty followup")
    return Option(id=raw["id"], label=raw["label"], followup=followup)


def _parse_question(raw: dict) -> Question:
    qid = raw.get("id")
    if not isinstance(qid, str) or not qid:
        raise QuestionConfigError("question missing 'id'")
    for key in ("category", "text", "type"):
        if not isinstance(raw.get(key), str) or not raw[key]:
            raise QuestionConfigError(f"question '{qid}': missing '{key}'")
    if raw["type"] not in ("single", "multi"):
        raise QuestionConfigError(f"question '{qid}': type must be 'single' or 'multi'")

    raw_options = raw.get("options")
    if not isinstance(raw_options, list) or not raw_options:
        raise QuestionConfigError(f"question '{qid}': must have non-empty 'options'")
    options = tuple(_parse_option(o, qid) for o in raw_options)

    option_ids = [o.id for o in options]
    if len(set(option_ids)) != len(option_ids):
        raise QuestionConfigError(f"question '{qid}': duplicate option id")

    select = raw.get("select")
    if raw["type"] == "multi":
        if not isinstance(select, int) or not (1 <= select <= len(options)):
            raise QuestionConfigError(
                f"question '{qid}': multi 'select' must be int in 1..{len(options)}"
            )
    elif select is not None:
        raise QuestionConfigError(f"question '{qid}': 'select' only valid for multi")

    return Question(
        id=qid,
        category=raw["category"],
        text=raw["text"],
        type=raw["type"],
        options=options,
        select=select,
    )


def load_questions(path: str | Path) -> list[Question]:
    """Load, validate, and return questions in file order. Fails fast on error."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise QuestionConfigError("questions.json must be an array with at least one question")

    questions = [_parse_question(item) for item in raw]

    ids = [q.id for q in questions]
    if len(set(ids)) != len(ids):
        raise QuestionConfigError("duplicate question id in questions.json")

    return questions
```

- [ ] **Step 5: Create `src/questions.json` with all 10 spec questions**

```json
[
  {
    "id": "food_adventure",
    "category": "Food adventurousness",
    "type": "single",
    "text": "Your last meal on earth would be?",
    "options": [
      {"id": "ramen", "label": "🍜 Ramen"},
      {"id": "sushi", "label": "🍣 Sushi"},
      {"id": "pizza", "label": "🍕 Pizza"},
      {"id": "burger", "label": "🍔 Burger"}
    ]
  },
  {
    "id": "dietary",
    "category": "Dietary needs",
    "type": "single",
    "text": "Anything we should know about food?",
    "options": [
      {"id": "none", "label": "No restrictions"},
      {"id": "vegetarian", "label": "🥗 Vegetarian"},
      {"id": "vegan", "label": "🌱 Vegan"},
      {"id": "allergies", "label": "⚠️ Allergies", "followup": "Type your allergies, separated by commas:"}
    ]
  },
  {
    "id": "drink",
    "category": "Drink preference",
    "type": "single",
    "text": "Pick your poison:",
    "options": [
      {"id": "coffee", "label": "☕ Coffee"},
      {"id": "wine", "label": "🍷 Wine"},
      {"id": "beer", "label": "🍺 Beer"},
      {"id": "cocktails", "label": "🍸 Cocktails"},
      {"id": "none", "label": "🚱 None"}
    ]
  },
  {
    "id": "pace",
    "category": "Pace",
    "type": "single",
    "text": "Your ideal travel day is...",
    "options": [
      {"id": "cram", "label": "Cram everything in"},
      {"id": "one_big", "label": "One big thing per day"},
      {"id": "zero_plans", "label": "Zero plans is the dream"}
    ]
  },
  {
    "id": "crowds",
    "category": "Crowds",
    "type": "single",
    "text": "Where do you want to go?",
    "options": [
      {"id": "bucket_list", "label": "Bucket-list spots"},
      {"id": "hidden_gems", "label": "Hidden gems"},
      {"id": "any", "label": "Doesn't matter"}
    ]
  },
  {
    "id": "vibe_mix",
    "category": "Vibe mix",
    "type": "multi",
    "select": 2,
    "text": "Pick your top 2 trip vibes:",
    "options": [
      {"id": "nature", "label": "🌿 Nature"},
      {"id": "culture", "label": "🏛 Culture"},
      {"id": "food", "label": "🍴 Food"},
      {"id": "nightlife", "label": "🌃 Nightlife"}
    ]
  },
  {
    "id": "body_clock",
    "category": "Body clock",
    "type": "single",
    "text": "When are you most alive?",
    "options": [
      {"id": "morning", "label": "🌅 Morning person"},
      {"id": "night_owl", "label": "🦉 Night owl"},
      {"id": "flexible", "label": "🤷 Flexible"}
    ]
  },
  {
    "id": "budget",
    "category": "Budget tier",
    "type": "single",
    "text": "What's the spending vibe?",
    "options": [
      {"id": "backpacker", "label": "🎒 Backpacker"},
      {"id": "mid", "label": "💳 Mid"},
      {"id": "splurge", "label": "💎 Splurge"},
      {"id": "mixed", "label": "🪙 Mixed"}
    ]
  },
  {
    "id": "effort",
    "category": "Physical effort tolerance",
    "type": "single",
    "text": "How hard do you want to push?",
    "options": [
      {"id": "all_day_hike", "label": "All-day hike"},
      {"id": "moderate", "label": "Moderate"},
      {"id": "minimal", "label": "Minimal"}
    ]
  },
  {
    "id": "spontaneity",
    "category": "Spontaneity",
    "type": "single",
    "text": "How much structure do you want?",
    "options": [
      {"id": "locked", "label": "Locked plans"},
      {"id": "loose", "label": "Loose framework"},
      {"id": "pure_vibes", "label": "Pure vibes"}
    ]
  }
]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_questions.py -v`
Expected: PASS (all tests, including `test_real_questions_json_is_valid`).

- [ ] **Step 7: Commit**

```bash
git add src/questions.py src/questions.json tests/test_questions.py tests/fixtures
git commit -m "feat: questions.json schema + validating loader

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Quiz engine (pure logic)

**Files:**
- Create: `src/quiz/engine.py`
- Test: `tests/test_engine.py`
- Create/Modify: `tests/conftest.py` (shared `sample_questions` fixture)

- [ ] **Step 1: Add shared fixture in `tests/conftest.py`**

Create `tests/conftest.py`:
```python
from pathlib import Path

import pytest

from src.questions import load_questions

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_questions():
    # food_adventure (single), dietary (single+followup), vibe_mix (multi select 2)
    return load_questions(FIXTURES / "valid_questions.json")
```

- [ ] **Step 2: Write the failing tests**

`tests/test_engine.py`:
```python
from src.quiz import engine


def test_next_question_returns_first_unanswered(sample_questions):
    q = engine.next_question(sample_questions, answered_ids=set())
    assert q.id == "food_adventure"


def test_next_question_skips_answered(sample_questions):
    q = engine.next_question(sample_questions, answered_ids={"food_adventure"})
    assert q.id == "dietary"


def test_next_question_none_when_all_answered(sample_questions):
    answered = {"food_adventure", "dietary", "vibe_mix"}
    assert engine.next_question(sample_questions, answered) is None


def test_is_complete(sample_questions):
    assert not engine.is_quiz_complete(sample_questions, set())
    assert engine.is_quiz_complete(
        sample_questions, {"food_adventure", "dietary", "vibe_mix"}
    )


def test_find_question_and_option(sample_questions):
    q = engine.find_question(sample_questions, "dietary")
    assert q.category == "Dietary needs"
    assert engine.find_question(sample_questions, "nope") is None
    assert engine.find_option(q, "allergies").label == "⚠️ Allergies"
    assert engine.find_option(q, "nope") is None


def test_option_followup(sample_questions):
    dietary = engine.find_question(sample_questions, "dietary")
    assert engine.option_followup(dietary, "allergies").startswith("Type your allergies")
    assert engine.option_followup(dietary, "none") is None


def test_toggle_adds_and_removes():
    assert engine.toggle_selection([], "nature", select_n=2) == ["nature"]
    assert engine.toggle_selection(["nature"], "food", select_n=2) == ["nature", "food"]
    assert engine.toggle_selection(["nature", "food"], "nature", select_n=2) == ["food"]


def test_toggle_caps_at_select_n():
    # Adding a third when 2 already chosen is ignored.
    assert engine.toggle_selection(["nature", "food"], "culture", select_n=2) == [
        "nature",
        "food",
    ]
    # Removing still works at the cap.
    assert engine.toggle_selection(["nature", "food"], "food", select_n=2) == ["nature"]


def test_is_selection_complete():
    assert not engine.is_selection_complete(["nature"], select_n=2)
    assert engine.is_selection_complete(["nature", "food"], select_n=2)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.quiz.engine'`.

- [ ] **Step 4: Implement `src/quiz/engine.py`**

```python
"""Pure quiz logic — no Telegram, no DB. Drives question order and select-N state."""

from __future__ import annotations

from src.questions import Option, Question


def next_question(questions: list[Question], answered_ids: set[str]) -> Question | None:
    """First question (in order) whose id is not yet answered, or None if done."""
    for q in questions:
        if q.id not in answered_ids:
            return q
    return None


def is_quiz_complete(questions: list[Question], answered_ids: set[str]) -> bool:
    return next_question(questions, answered_ids) is None


def find_question(questions: list[Question], qid: str) -> Question | None:
    return next((q for q in questions if q.id == qid), None)


def find_option(question: Question, oid: str) -> Option | None:
    return next((o for o in question.options if o.id == oid), None)


def option_followup(question: Question, oid: str) -> str | None:
    opt = find_option(question, oid)
    return opt.followup if opt else None


def toggle_selection(current: list[str], oid: str, select_n: int) -> list[str]:
    """Toggle membership of oid. Adding beyond select_n is ignored (cap); removing always works."""
    if oid in current:
        return [o for o in current if o != oid]
    if len(current) >= select_n:
        return list(current)
    return [*current, oid]


def is_selection_complete(current: list[str], select_n: int) -> bool:
    return len(current) == select_n
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_engine.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/quiz/engine.py tests/test_engine.py tests/conftest.py
git commit -m "feat: pure quiz engine (ordering, select-N toggle, followup lookup)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Database schema

**Files:**
- Create: `src/db.py`
- Create: `src/config.py`
- Test: `tests/test_repos.py` (DB-init portion; repo tests added in Task 5)

- [ ] **Step 1: Implement `src/config.py`**

```python
"""Environment + path configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_PATH = Path(__file__).resolve().parent / "questions.json"
DB_PATH = ROOT / "quiz.db"


def get_bot_token() -> str:
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "BOT_TOKEN is not set. Copy .env.example to .env and add your BotFather token."
        )
    return token
```

- [ ] **Step 2: Write the failing test for schema init**

Add to `tests/test_repos.py` (create the file):
```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_repos.py -v`
Expected: FAIL — `AttributeError: module 'src.db' has no attribute 'init_schema'` (or import error).

- [ ] **Step 4: Implement `src/db.py`**

```python
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
"""


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def connect(path: str | Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_repos.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/config.py src/db.py tests/test_repos.py
git commit -m "feat: SQLite schema + config loader

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Repositories (users + answers)

**Files:**
- Create: `src/repos/users.py`
- Create: `src/repos/answers.py`
- Test: `tests/test_repos.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_repos.py`:
```python
from src.repos import answers as answers_repo
from src.repos import users as users_repo

NOW = "2026-05-30T12:00:00"


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_repos.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.repos.users'`.

- [ ] **Step 3: Implement `src/repos/users.py`**

```python
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
```

- [ ] **Step 4: Implement `src/repos/answers.py`**

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_repos.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/repos/users.py src/repos/answers.py tests/test_repos.py
git commit -m "feat: user + answer repositories with upsert and clear

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Profile renderer (pure)

**Files:**
- Create: `src/profile/render.py`
- Test: `tests/test_render.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_render.py`:
```python
import json

from src.profile import render


def test_render_single_uses_option_label(sample_questions):
    answers = {"food_adventure": "ramen"}
    text = render.render_profile(sample_questions, answers)
    assert "Food adventurousness" in text
    assert "🍜 Ramen" in text


def test_render_multi_joins_labels(sample_questions):
    answers = {"vibe_mix": json.dumps(["nature", "food"])}
    text = render.render_profile(sample_questions, answers)
    assert "🌿 Nature" in text
    assert "🍴 Food" in text


def test_render_followup_shows_free_text(sample_questions):
    # dietary 'allergies' option carries a followup; value is free text.
    answers = {"dietary": "peanuts, shellfish"}
    text = render.render_profile(sample_questions, answers)
    assert "Dietary needs" in text
    assert "peanuts, shellfish" in text


def test_render_unanswered_marked(sample_questions):
    text = render.render_profile(sample_questions, answers={})
    # Every category present; unanswered shown with a placeholder.
    assert "Food adventurousness" in text
    assert "—" in text


def test_render_is_complete_flag(sample_questions):
    complete = render.render_profile(
        sample_questions,
        {"food_adventure": "ramen", "dietary": "none", "vibe_mix": json.dumps(["nature", "food"])},
        is_complete=True,
    )
    assert "finish" not in complete.lower()

    partial = render.render_profile(sample_questions, {"food_adventure": "ramen"}, is_complete=False)
    assert "/start" in partial
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.profile.render'`.

- [ ] **Step 3: Implement `src/profile/render.py`**

```python
"""Render a user's saved answers into a Telegram profile message (pure, HTML-safe)."""

from __future__ import annotations

import json
from html import escape

from src.questions import Question

UNANSWERED = "—"


def _value_to_display(question: Question, value: str) -> str:
    label_by_id = {o.id: o.label for o in question.options}

    if question.type == "multi":
        try:
            ids = json.loads(value)
        except json.JSONDecodeError:
            return escape(value)
        return ", ".join(escape(label_by_id.get(i, i)) for i in ids)

    # single: a stored option id maps to its label; anything else is followup free text.
    if value in label_by_id:
        return escape(label_by_id[value])
    return escape(value)


def render_profile(
    questions: list[Question],
    answers: dict[str, str],
    *,
    is_complete: bool = True,
) -> str:
    lines = ["<b>Your travel profile</b>", ""]
    for q in questions:
        if q.id in answers:
            display = _value_to_display(q, answers[q.id])
        else:
            display = UNANSWERED
        lines.append(f"<b>{escape(q.category)}:</b> {display}")

    if not is_complete:
        lines += ["", "Some answers are missing — run /start to finish the quiz."]

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_render.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: ALL PASS (questions, engine, repos, render).

- [ ] **Step 6: Commit**

```bash
git add src/profile/render.py tests/test_render.py
git commit -m "feat: profile renderer (single/multi/followup, incomplete notice)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: FSM states + session helpers

**Files:**
- Create: `src/quiz/states.py`
- Create: `src/quiz/session.py`

> No automated test — these are thin wrappers over aiogram's `FSMContext`. They are exercised manually via the handlers in Task 9.

- [ ] **Step 1: Implement `src/quiz/states.py`**

```python
"""aiogram FSM states for the onboarding quiz."""

from aiogram.fsm.state import State, StatesGroup


class Quiz(StatesGroup):
    answering = State()          # showing questions, awaiting button taps
    awaiting_followup = State()  # awaiting a free-text reply (e.g. allergies)
```

- [ ] **Step 2: Implement `src/quiz/session.py`**

```python
"""Helpers over aiogram FSMContext for per-user quiz progress.

FSM data keys:
  selections   -> list[str]  in-progress option ids for the current multi question
  followup_qid -> str        question id awaiting a free-text followup
"""

from __future__ import annotations

from aiogram.fsm.context import FSMContext


async def get_selections(state: FSMContext) -> list[str]:
    data = await state.get_data()
    return list(data.get("selections", []))


async def set_selections(state: FSMContext, selections: list[str]) -> None:
    await state.update_data(selections=selections)


async def clear_selections(state: FSMContext) -> None:
    await state.update_data(selections=[])


async def set_followup_qid(state: FSMContext, qid: str) -> None:
    await state.update_data(followup_qid=qid)


async def get_followup_qid(state: FSMContext) -> str | None:
    data = await state.get_data()
    return data.get("followup_qid")
```

- [ ] **Step 3: Verify imports load**

Run: `python -c "import src.quiz.states, src.quiz.session; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add src/quiz/states.py src/quiz/session.py
git commit -m "feat: quiz FSM states and session helpers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Keyboard builders (pure)

**Files:**
- Modify: `src/quiz/engine.py` (add keyboard-data builders)
- Test: `tests/test_engine.py` (extend)

> Build keyboard **data** (lists of `(label, callback_data)`) as pure functions so they are testable; the handler converts them to aiogram `InlineKeyboardMarkup`. Callback format: `q:{qid}:{oid}` for an option tap, `done:{qid}` for the multi Done button.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine.py`:
```python
def test_single_keyboard_rows(sample_questions):
    q = engine.find_question(sample_questions, "food_adventure")
    rows = engine.build_keyboard(q, selections=[])
    # One button per option, each its own row; callback q:<qid>:<oid>.
    assert rows == [
        [("🍜 Ramen", "q:food_adventure:ramen")],
        [("🍣 Sushi", "q:food_adventure:sushi")],
    ]


def test_multi_keyboard_marks_selected_and_adds_done(sample_questions):
    q = engine.find_question(sample_questions, "vibe_mix")
    rows = engine.build_keyboard(q, selections=["nature"])
    labels = [btn[0] for row in rows for btn in row]
    assert "✅ 🌿 Nature" in labels   # selected gets a check prefix
    assert "🏛 Culture" in labels      # unselected unchanged
    # Last row is the Done button.
    assert rows[-1] == [("✔️ Done (1/2)", "done:vibe_mix")]


def test_parse_callback():
    assert engine.parse_callback("q:vibe_mix:nature") == ("q", "vibe_mix", "nature")
    assert engine.parse_callback("done:vibe_mix") == ("done", "vibe_mix", None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_engine.py -v`
Expected: FAIL — `AttributeError: module 'src.quiz.engine' has no attribute 'build_keyboard'`.

- [ ] **Step 3: Add builders to `src/quiz/engine.py`**

Append to `src/quiz/engine.py`:
```python
def build_keyboard(question: Question, selections: list[str]) -> list[list[tuple[str, str]]]:
    """Return rows of (label, callback_data). One option per row.

    For multi questions, selected options get a ✅ prefix and a Done row is appended.
    """
    rows: list[list[tuple[str, str]]] = []
    for opt in question.options:
        label = opt.label
        if question.type == "multi" and opt.id in selections:
            label = f"✅ {opt.label}"
        rows.append([(label, f"q:{question.id}:{opt.id}")])

    if question.type == "multi":
        count = len(selections)
        rows.append([(f"✔️ Done ({count}/{question.select})", f"done:{question.id}")])

    return rows


def parse_callback(data: str) -> tuple[str, str, str | None]:
    """Parse callback_data. 'q:<qid>:<oid>' -> ('q', qid, oid); 'done:<qid>' -> ('done', qid, None)."""
    parts = data.split(":")
    if parts[0] == "q":
        return ("q", parts[1], parts[2])
    if parts[0] == "done":
        return ("done", parts[1], None)
    raise ValueError(f"unknown callback data: {data}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_engine.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quiz/engine.py tests/test_engine.py
git commit -m "feat: pure keyboard builders + callback parser for quiz

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Telegram handlers

**Files:**
- Create: `src/quiz/handlers.py`

> Handlers are thin glue: translate Telegram events into engine/repo calls. No automated tests (spec: no live-bot tests in Phase 1). Verified manually in Task 10.

- [ ] **Step 1: Implement `src/quiz/handlers.py`**

```python
"""aiogram Router: quiz commands, option callbacks, and followup text."""

from __future__ import annotations

import json
import sqlite3

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.profile.render import render_profile
from src.questions import Question
from src.quiz import engine, session
from src.quiz.states import Quiz

router = Router()


def _now() -> str:
    # datetime.now() imported locally so tests/imports stay light.
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _markup(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=data) for label, data in row]
            for row in rows
        ]
    )


def _conn(message_or_cb) -> sqlite3.Connection:
    # The connection + questions are stashed on the bot via workflow data (set in bot.py).
    return message_or_cb.bot["conn"]


def _questions(message_or_cb) -> list[Question]:
    return message_or_cb.bot["questions"]


async def _send_next_or_finish(target, state: FSMContext, conn, questions, user_id: int) -> None:
    answered = set(__import__("src.repos.answers", fromlist=["get_answers"]).get_answers(conn, user_id))
    q = engine.next_question(questions, answered)
    if q is None:
        from src.repos import users as users_repo

        users_repo.set_completed_at(conn, user_id, when=_now())
        await state.clear()
        await target.answer("🎉 All done! Here's your profile:")
        answers = __import__("src.repos.answers", fromlist=["get_answers"]).get_answers(conn, user_id)
        await target.answer(render_profile(questions, answers, is_complete=True), parse_mode="HTML")
        return

    await session.clear_selections(state)
    await state.set_state(Quiz.answering)
    rows = engine.build_keyboard(q, selections=[])
    await target.answer(q.text, reply_markup=_markup(rows))


@router.message(Command("start"))
@router.message(Command("restart"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    from src.repos import answers as answers_repo
    from src.repos import users as users_repo

    conn = _conn(message)
    questions = _questions(message)
    user = message.from_user
    users_repo.upsert_user(
        conn, user.id, username=user.username, first_name=user.first_name, now=_now()
    )
    answers_repo.clear_answers(conn, user.id)
    await state.clear()
    await message.answer("Let's build your travel profile! A few quick taps. 🧭")
    await _send_next_or_finish(message, state, conn, questions, user.id)


@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    from src.repos import answers as answers_repo
    from src.repos import users as users_repo

    conn = _conn(message)
    questions = _questions(message)
    user_row = users_repo.get_user(conn, message.from_user.id)
    if user_row is None:
        await message.answer("No profile yet — run /start to begin.")
        return
    answers = answers_repo.get_answers(conn, message.from_user.id)
    is_complete = user_row["completed_at"] is not None
    await message.answer(
        render_profile(questions, answers, is_complete=is_complete), parse_mode="HTML"
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "I'm your travel companion (in training).\n"
        "/start — take the onboarding quiz\n"
        "/restart — redo the quiz\n"
        "/profile — see your saved profile"
    )


@router.callback_query(Quiz.answering, F.data.startswith("q:"))
async def on_option(cb: CallbackQuery, state: FSMContext) -> None:
    from src.repos import answers as answers_repo

    conn = _conn(cb)
    questions = _questions(cb)
    _, qid, oid = engine.parse_callback(cb.data)
    question = engine.find_question(questions, qid)
    if question is None or engine.find_option(question, oid) is None:
        await cb.answer("That option expired — /restart to redo.")
        return

    if question.type == "single":
        followup = engine.option_followup(question, oid)
        if followup:
            await session.set_followup_qid(state, qid)
            await state.set_state(Quiz.awaiting_followup)
            await cb.message.answer(followup)
            await cb.answer()
            return
        answers_repo.upsert_answer(conn, cb.from_user.id, qid, oid, now=_now())
        await cb.answer("Saved ✅")
        await _send_next_or_finish(cb.message, state, conn, questions, cb.from_user.id)
        return

    # multi: toggle, re-render in place.
    selections = await session.get_selections(state)
    selections = engine.toggle_selection(selections, oid, question.select)
    await session.set_selections(state, selections)
    rows = engine.build_keyboard(question, selections=selections)
    await cb.message.edit_reply_markup(reply_markup=_markup(rows))
    await cb.answer()


@router.callback_query(Quiz.answering, F.data.startswith("done:"))
async def on_done(cb: CallbackQuery, state: FSMContext) -> None:
    from src.repos import answers as answers_repo

    conn = _conn(cb)
    questions = _questions(cb)
    _, qid, _oid = engine.parse_callback(cb.data)
    question = engine.find_question(questions, qid)
    selections = await session.get_selections(state)
    if question is None or not engine.is_selection_complete(selections, question.select):
        await cb.answer(f"Pick exactly {question.select if question else '?'}.", show_alert=False)
        return
    answers_repo.upsert_answer(conn, cb.from_user.id, qid, json.dumps(selections), now=_now())
    await cb.answer("Saved ✅")
    await _send_next_or_finish(cb.message, state, conn, questions, cb.from_user.id)


@router.message(Quiz.awaiting_followup, F.text)
async def on_followup_text(message: Message, state: FSMContext) -> None:
    from src.repos import answers as answers_repo

    conn = _conn(message)
    questions = _questions(message)
    qid = await session.get_followup_qid(state)
    if qid is None:
        await message.answer("Something got out of sync — /restart to redo.")
        return
    answers_repo.upsert_answer(conn, message.from_user.id, qid, message.text.strip(), now=_now())
    await _send_next_or_finish(message, state, conn, questions, message.from_user.id)


@router.message()
async def fallback(message: Message) -> None:
    await message.answer("Tap the buttons above, or use /start to (re)take the quiz.")
```

> Note for the implementer: `message.bot["conn"]` / `message.bot["questions"]` use aiogram's `Bot` mapping set up in Task 10. The `__import__(...)` calls for `answers` avoid a circular import at module load; you may instead move `from src.repos import answers as answers_repo` to module top if no circular import appears — verify with `python -c "import src.quiz.handlers"`.

- [ ] **Step 2: Verify the module imports**

Run: `python -c "import src.quiz.handlers; print('ok')"`
Expected: prints `ok`. If an ImportError about circular imports appears, keep the function-local imports as written.

- [ ] **Step 3: Commit**

```bash
git add src/quiz/handlers.py
git commit -m "feat: Telegram quiz handlers (start/restart/profile/help, callbacks, followup)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Bot entrypoint + wiring

**Files:**
- Create: `src/bot.py`

- [ ] **Step 1: Implement `src/bot.py`**

```python
"""Entrypoint: build the bot, load data, start long-polling."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from src.config import QUESTIONS_PATH, get_bot_token
from src.db import connect
from src.questions import load_questions
from src.quiz.handlers import router

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    token = get_bot_token()
    questions = load_questions(QUESTIONS_PATH)  # fail fast if content invalid
    conn = connect()

    bot = Bot(token)
    # Stash shared dependencies on the bot for handlers to read.
    bot["conn"] = conn
    bot["questions"] = questions

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    logging.info("Loaded %d questions. Starting long-polling…", len(questions))
    try:
        await dp.start_polling(bot)
    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
```

> If aiogram's `Bot` does not support item assignment in the installed version, replace `bot["conn"]`/`bot["questions"]` with a module-level holder object imported by `handlers.py` (e.g. a small `Deps` dataclass set in `main()` and read via a getter). Verify the chosen approach at Step 3.

- [ ] **Step 2: Run the full automated suite once more**

Run: `pytest -v`
Expected: ALL PASS.

- [ ] **Step 3: Manual smoke test against real Telegram**

1. Create a bot: in Telegram, message **@BotFather** → `/newbot` → follow prompts → copy the token.
2. `copy .env.example .env` (PowerShell: `Copy-Item .env.example .env`) and paste the token after `BOT_TOKEN=`.
3. Run: `python -m src.bot`
   Expected log: `Loaded 10 questions. Starting long-polling…`
4. In Telegram, open your bot, send `/start`. Walk the full quiz:
   - Single questions: one tap advances.
   - Choose **Allergies** on the dietary question → bot asks for text → type "peanuts" → advances.
   - Vibe mix: tap two options (checks appear), tap **Done** → advances; try tapping a third (ignored), try **Done** with one selected (toast asks for exactly 2).
   - Finish → profile appears.
5. Send `/profile` → see saved profile.
6. Stop the bot (Ctrl+C), restart `python -m src.bot`, send `/profile` → profile persists.
7. Send `/start` again → answers reset, quiz restarts from Q1.

Expected: all steps behave as described. Fix any wiring issues (most likely the `bot["..."]` accessor — see Step 1 note) before committing.

- [ ] **Step 4: Commit**

```bash
git add src/bot.py
git commit -m "feat: bot entrypoint with long-polling and dependency wiring

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# Travel Companion Bot — Phase 1 (Onboarding Quiz)

A Telegram bot that runs a short multiple-choice onboarding quiz and saves each
user's travel profile. Phase 1 of the travel companion project (see
`travel-companion-bot-requirements.md`). No LLM yet.

## Setup

Requires Python 3.11+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Create a bot token

1. In Telegram, message **@BotFather**.
2. Send `/newbot`, choose a name and username.
3. Copy the token it gives you.
4. `Copy-Item .env.example .env` and set `BOT_TOKEN=<your token>`.

`.env` is gitignored — never commit your token.

## Run

```powershell
python -m src.bot
```

Then open your bot in Telegram and send `/start`.

## Commands

- `/start` — take the onboarding quiz (restarts if already taken)
- `/restart` — redo the quiz
- `/profile` — view your saved profile
- `/help` — list commands

## Editing the quiz (no code needed)

Quiz content lives in `src/questions.json`. Each question has an `id`,
`category`, `text`, `type` (`single` or `multi`), and `options`. For a
"pick N" question use `"type": "multi"` with `"select": N`. An option can carry
a `"followup": "<prompt>"` to ask for free-text after it's chosen (e.g.
allergies). The bot validates this file on startup and refuses to run if it's
malformed.

## Tests

```powershell
pytest
```

Pure logic (question loading, quiz engine, profile rendering, repositories) is
covered by tests. Telegram handlers are verified manually (see the quiz flow in
the project plan).
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with setup, BotFather, run, and quiz-editing guide

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final Verification

- [ ] Run full suite: `pytest -v` → all green.
- [ ] Manual Telegram smoke test (Task 10 Step 3) passed end-to-end.
- [ ] `/start` → 10 questions → `/profile` works for the builder.
- [ ] Profile persists across a bot restart.
- [ ] questions.json edit (change a label) reflects after restart with no code change.

## Acceptance criteria (from spec)

- [ ] Builder and wife can `/start`, answer all 10 questions, and see `/profile`.
- [ ] Profile persists across bot restarts.
- [ ] The two friends can also onboard themselves.
- [ ] The quiz feels fun, takes ≤ 2 minutes.
