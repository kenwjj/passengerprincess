from pathlib import Path

import pytest

from src.questions import (
    Option,
    Question,
    QuestionConfigError,
    load_questions,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_valid_returns_questions_in_order():
    questions = load_questions(FIXTURES / "valid_questions.json")
    assert [q.id for q in questions] == ["food_adventure", "dietary", "vibe_mix"]
    assert isinstance(questions[0], Question)
    assert isinstance(questions[0].options[0], Option)


def test_single_question_parsed():
    q = load_questions(FIXTURES / "valid_questions.json")[0]
    assert q.type == "single"
    assert q.select is None
    assert q.options[0].id == "ramen"
    assert q.options[0].label == "🍜 Ramen"
    assert q.options[0].followup is None


def test_followup_option_parsed():
    dietary = load_questions(FIXTURES / "valid_questions.json")[1]
    allergies = dietary.options[1]
    assert allergies.id == "allergies"
    assert allergies.followup == "Type your allergies, separated by commas:"


def test_multi_question_parsed():
    vibe = load_questions(FIXTURES / "valid_questions.json")[2]
    assert vibe.type == "multi"
    assert vibe.select == 2
    assert len(vibe.options) == 3


def test_duplicate_question_ids_rejected():
    with pytest.raises(QuestionConfigError, match="duplicate question id"):
        load_questions(FIXTURES / "invalid_dup_ids.json")


def test_empty_array_rejected(tmp_path):
    p = tmp_path / "empty.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(QuestionConfigError, match="at least one question"):
        load_questions(p)


def test_multi_without_valid_select_rejected(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(
        '[{"id":"q","category":"C","type":"multi","text":"?",'
        '"options":[{"id":"a","label":"A"}],"select":2}]',
        encoding="utf-8",
    )
    with pytest.raises(QuestionConfigError, match="select"):
        load_questions(p)


def test_real_questions_json_is_valid():
    # The shipped content file must always load.
    questions = load_questions(Path("src/questions.json"))
    assert len(questions) == 10
