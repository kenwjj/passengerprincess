from src.quiz import engine


def test_next_question_returns_first_unanswered(sample_questions):
    q = engine.next_question(sample_questions, answered_ids=set())
    assert q.id == "food_adventure"


def test_next_question_skips_answered(sample_questions):
    q = engine.next_question(sample_questions, answered_ids={"food_adventure"})
    assert q.id == "dietary"


def test_next_question_none_when_all_answered(sample_questions):
    answered = {"food_adventure", "dietary", "vibe_mix"}
    assert engine.next_question(sample_questions, answered) is None


def test_is_complete(sample_questions):
    assert not engine.is_quiz_complete(sample_questions, set())
    assert engine.is_quiz_complete(
        sample_questions, {"food_adventure", "dietary", "vibe_mix"}
    )


def test_find_question_and_option(sample_questions):
    q = engine.find_question(sample_questions, "dietary")
    assert q.category == "Dietary needs"
    assert engine.find_question(sample_questions, "nope") is None
    assert engine.find_option(q, "allergies").label == "Allergies"
    assert engine.find_option(q, "nope") is None


def test_option_followup(sample_questions):
    dietary = engine.find_question(sample_questions, "dietary")
    assert engine.option_followup(dietary, "allergies").startswith("Type your allergies")
    assert engine.option_followup(dietary, "none") is None


def test_toggle_adds_and_removes():
    assert engine.toggle_selection([], "nature", select_n=2) == ["nature"]
    assert engine.toggle_selection(["nature"], "food", select_n=2) == ["nature", "food"]
    assert engine.toggle_selection(["nature", "food"], "nature", select_n=2) == ["food"]


def test_toggle_caps_at_select_n():
    # Adding a third when 2 already chosen is ignored.
    assert engine.toggle_selection(["nature", "food"], "culture", select_n=2) == [
        "nature",
        "food",
    ]
    # Removing still works at the cap.
    assert engine.toggle_selection(["nature", "food"], "food", select_n=2) == ["nature"]


def test_is_selection_complete():
    assert not engine.is_selection_complete(["nature"], select_n=2)
    assert engine.is_selection_complete(["nature", "food"], select_n=2)
