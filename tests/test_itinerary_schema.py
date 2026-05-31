import pytest

from src.trip import schema

START, END = "2026-10-24", "2026-10-25"  # 2 days


def _good_raw():
    return {
        "trip_summary": "A balanced Jeju coastal ride.",
        "days": [
            {
                "day_number": 1, "date": "2026-10-24",
                "title": "West coast", "summary": "Easy start.",
                "stops": [
                    {"name": "Aewol", "type": "ride", "arrive": "09:00",
                     "depart": "10:30", "note": "Coffee with a view."},
                ],
                "daylight_note": "Finishes well before sunset.",
            },
            {
                "day_number": 2, "date": "2026-10-25",
                "title": "South coast", "summary": "Longer push.",
                "stops": [
                    {"name": "Jungmun", "type": "sight", "arrive": None,
                     "depart": None, "note": "Cliffs."},
                ],
                "daylight_note": "Tight; start early.",
            },
        ],
    }


def test_validate_accepts_good_itinerary():
    itin = schema.validate(_good_raw(), start_date=START, end_date=END)
    assert itin.trip_summary.startswith("A balanced")
    assert len(itin.days) == 2
    assert itin.days[0].stops[0].name == "Aewol"
    assert itin.days[1].stops[0].arrive is None


def test_validate_rejects_bad_stop_type():
    raw = _good_raw()
    raw["days"][0]["stops"][0]["type"] = "teleport"
    with pytest.raises(schema.ItineraryError, match="type"):
        schema.validate(raw, start_date=START, end_date=END)


def test_validate_rejects_wrong_day_count():
    raw = _good_raw()
    raw["days"].pop()  # only 1 day for a 2-day range
    with pytest.raises(schema.ItineraryError, match="day"):
        schema.validate(raw, start_date=START, end_date=END)


def test_validate_rejects_date_out_of_range():
    raw = _good_raw()
    raw["days"][1]["date"] = "2026-11-01"
    with pytest.raises(schema.ItineraryError, match="range"):
        schema.validate(raw, start_date=START, end_date=END)


def test_validate_rejects_missing_field():
    raw = _good_raw()
    del raw["days"][0]["title"]
    with pytest.raises(schema.ItineraryError):
        schema.validate(raw, start_date=START, end_date=END)


def test_from_dict_roundtrip():
    itin = schema.validate(_good_raw(), start_date=START, end_date=END)
    rebuilt = schema.Itinerary.from_dict(_good_raw())
    assert rebuilt.days[0].title == itin.days[0].title
