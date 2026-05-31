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
