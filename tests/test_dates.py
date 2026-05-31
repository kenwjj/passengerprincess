from datetime import date

import pytest

from src.trip import dates

REF = date(2026, 6, 1)  # fixed "today" for determinism


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Oct 24-28", ("2026-10-24", "2026-10-28")),
        ("Oct 24 to 28", ("2026-10-24", "2026-10-28")),
        ("October 24 - 28", ("2026-10-24", "2026-10-28")),
        ("2026-10-24 to 2026-10-28", ("2026-10-24", "2026-10-28")),
        ("2026-10-24 - 2026-10-28", ("2026-10-24", "2026-10-28")),
    ],
)
def test_parse_common_range_forms(raw, expected):
    assert dates.parse_date_range(raw, reference=REF) == expected


def test_single_date_is_one_day_trip():
    assert dates.parse_date_range("2026-10-24", reference=REF) == (
        "2026-10-24",
        "2026-10-24",
    )


def test_bare_month_day_rolls_forward_when_in_the_past():
    # Reference is December; a bare "Oct 24-28" (no year) resolves to NEXT year.
    assert dates.parse_date_range("Oct 24-28", reference=date(2026, 12, 1)) == (
        "2027-10-24",
        "2027-10-28",
    )


def test_explicit_year_is_not_rolled_forward():
    # Explicit 2026 dates earlier than the reference stay in 2026 (year was given).
    assert dates.parse_date_range(
        "2026-01-10 to 2026-01-15", reference=date(2026, 6, 1)
    ) == ("2026-01-10", "2026-01-15")


def test_parse_rejects_gibberish():
    with pytest.raises(dates.DateParseError):
        dates.parse_date_range("sometime soon-ish", reference=REF)


def test_validate_rejects_reversed_range():
    with pytest.raises(dates.DateParseError, match="precede"):
        dates.validate_date_range("2026-10-28", "2026-10-24")


def test_validate_rejects_unparseable():
    with pytest.raises(dates.DateParseError):
        dates.validate_date_range("not-a-date", "2026-10-28")


def test_validate_rejects_overlong_span():
    with pytest.raises(dates.DateParseError, match="long"):
        dates.validate_date_range("2026-01-01", "2026-06-01")
