from src.trip import prompt


def test_system_prompt_states_rules():
    sys = prompt.build_system_prompt()
    assert "emit_itinerary" in sys
    assert "every" in sys.lower()  # respect every member's profile
    assert "sunset" in sys.lower()


def test_user_prompt_includes_all_inputs():
    out = prompt.build_user_prompt(
        destination="Jeju",
        start_date="2026-10-24",
        end_date="2026-10-28",
        activity="cycling",
        sunset="17:45",
        member_summaries=["Ken: Food: Ramen", "Amy: Vibe: Nature"],
    )
    assert "Jeju" in out
    assert "2026-10-24" in out and "2026-10-28" in out
    assert "5" in out  # 5-day count
    assert "cycling" in out
    assert "17:45" in out
    assert "Ken: Food: Ramen" in out
    assert "Amy: Vibe: Nature" in out
