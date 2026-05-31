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
