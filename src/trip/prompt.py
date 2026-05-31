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
