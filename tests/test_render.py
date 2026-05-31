import json

from src.profile import render


def test_render_single_uses_option_label(sample_questions):
    answers = {"food_adventure": "ramen"}
    text = render.render_profile(sample_questions, answers)
    assert "Food adventurousness" in text
    assert "🍜 Ramen" in text


def test_render_multi_joins_labels(sample_questions):
    answers = {"vibe_mix": json.dumps(["nature", "food"])}
    text = render.render_profile(sample_questions, answers)
    assert "🌿 Nature" in text
    assert "🍴 Food" in text


def test_render_followup_shows_free_text(sample_questions):
    # dietary 'allergies' option carries a followup; value is free text.
    answers = {"dietary": "peanuts, shellfish"}
    text = render.render_profile(sample_questions, answers)
    assert "Dietary needs" in text
    assert "peanuts, shellfish" in text


def test_render_unanswered_marked(sample_questions):
    text = render.render_profile(sample_questions, answers={})
    # Every category present; unanswered shown with a placeholder.
    assert "Food adventurousness" in text
    assert "—" in text


def test_render_is_complete_flag(sample_questions):
    complete = render.render_profile(
        sample_questions,
        {"food_adventure": "ramen", "dietary": "none", "vibe_mix": json.dumps(["nature", "food"])},
        is_complete=True,
    )
    assert "finish" not in complete.lower()

    partial = render.render_profile(sample_questions, {"food_adventure": "ramen"}, is_complete=False)
    assert "/start" in partial
