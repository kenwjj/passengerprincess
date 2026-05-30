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
