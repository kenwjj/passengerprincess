from src.trip import wizard


def test_activity_options_are_three_known_ids():
    ids = {oid for _label, oid in wizard.ACTIVITY_OPTIONS}
    assert ids == {"cycling", "self_drive", "general"}


def test_toggle_member_adds_and_removes_but_locks_creator():
    current = [1]  # creator
    assert wizard.toggle_member(current, 2, locked=1) == [1, 2]
    assert wizard.toggle_member([1, 2], 2, locked=1) == [1]
    # creator can never be removed
    assert wizard.toggle_member([1, 2], 1, locked=1) == [1, 2]


def test_member_keyboard_marks_selected_and_locks_creator():
    users = [
        {"telegram_user_id": 1, "first_name": "Ken", "username": "k"},
        {"telegram_user_id": 2, "first_name": "Amy", "username": "a"},
    ]
    rows = wizard.member_keyboard(users, selected=[1], locked=1)
    flat = {data: label for row in rows for label, data in row}
    # creator row shows a lock; selected shows a check; Done row present
    assert any("🔒" in label for label in flat.values())
    assert any(data == "memdone" for row in rows for _l, data in row)
    assert "mem:2" in flat


def test_day_count_inclusive():
    assert wizard.day_count("2026-10-24", "2026-10-28") == 5


def test_confirm_summary_contains_inputs():
    out = wizard.confirm_summary(
        destination="Jeju", start_date="2026-10-24", end_date="2026-10-28",
        activity="cycling", member_names=["Ken", "Amy"],
    )
    assert "Jeju" in out and "cycling" in out
    assert "Ken" in out and "Amy" in out
    assert "5" in out
