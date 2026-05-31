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
