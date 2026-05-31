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
