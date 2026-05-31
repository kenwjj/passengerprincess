from src.questions import Option, Question
from src.profile.summary import summarize_profile

QUESTIONS = [
    Question(
        id="food_adventure", category="Food", text="?", type="single",
        options=(Option("ramen", "🍜 Ramen"), Option("sushi", "🍣 Sushi")),
    ),
    Question(
        id="vibe_mix", category="Vibe", text="?", type="multi", select=2,
        options=(Option("nature", "🌿 Nature"), Option("food", "🍴 Food")),
    ),
    Question(
        id="dietary", category="Dietary", text="?", type="single",
        options=(Option("allergies", "⚠️ Allergies", "type them"),),
    ),
]


def test_summary_maps_ids_to_labels():
    answers = {"food_adventure": "ramen", "vibe_mix": '["nature", "food"]'}
    out = summarize_profile(QUESTIONS, answers)
    assert "Food: 🍜 Ramen" in out
    assert "Vibe: 🌿 Nature, 🍴 Food" in out


def test_summary_keeps_freetext_followup_value():
    answers = {"dietary": "peanuts, shellfish"}
    out = summarize_profile(QUESTIONS, answers)
    assert "Dietary: peanuts, shellfish" in out


def test_summary_skips_unanswered():
    out = summarize_profile(QUESTIONS, {"food_adventure": "sushi"})
    assert "Vibe" not in out
    assert "Dietary" not in out
