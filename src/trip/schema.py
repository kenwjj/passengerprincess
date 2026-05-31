"""Itinerary data model, the emit_itinerary tool contract, and validation (pure)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

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
    return [(start + timedelta(days=i)).isoformat() for i in range(span + 1)]


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
