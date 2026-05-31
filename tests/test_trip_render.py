from src.trip import schema
from src.trip import render

START, END = "2026-10-24", "2026-10-24"  # 1 day


def _itin():
    raw = {
        "trip_summary": "Coastal & chill.",
        "days": [
            {
                "day_number": 1, "date": "2026-10-24",
                "title": "West coast", "summary": "Easy start.",
                "stops": [
                    {"name": "Aewol <Cafe>", "type": "food", "arrive": "09:00",
                     "depart": "10:30", "note": "Sea view."},
                    {"name": "Hallim", "type": "ride", "arrive": None,
                     "depart": None, "note": "Flat path."},
                ],
                "daylight_note": "Plenty of daylight.",
            },
        ],
    }
    return schema.validate(raw, start_date=START, end_date=END)


def test_render_itinerary_returns_lead_plus_one_per_day():
    msgs = render.render_itinerary(_itin(), member_names=["Ken", "Amy"])
    assert len(msgs) == 2  # lead + 1 day
    assert "Coastal &amp; chill." in msgs[0]  # summary HTML-escaped
    assert "Ken" in msgs[0] and "Amy" in msgs[0]
    assert "estimate" in msgs[0].lower()  # disclaimer present


def test_render_day_escapes_and_formats():
    day_msg = render.render_day(_itin().days[0])
    assert "Day 1" in day_msg
    assert "West coast" in day_msg
    assert "Aewol &lt;Cafe&gt;" in day_msg  # HTML-escaped stop name
    assert "09:00" in day_msg and "10:30" in day_msg
    assert "Plenty of daylight." in day_msg


def test_render_trips_list_marks_generated_state():
    rows = [
        {"id": 7, "destination": "Jeju", "start_date": "2026-10-24",
         "end_date": "2026-10-28", "itinerary_json": "{}"},
        {"id": 8, "destination": "Busan", "start_date": "2026-11-01",
         "end_date": "2026-11-03", "itinerary_json": None},
    ]
    out = render.render_trips_list(rows)
    assert "Jeju" in out and "Busan" in out
    assert "not generated" in out.lower()  # the NULL-itinerary trip
