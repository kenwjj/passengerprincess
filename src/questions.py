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
