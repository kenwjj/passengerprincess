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
