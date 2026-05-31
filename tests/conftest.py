from pathlib import Path

import pytest

from src.questions import load_questions

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_questions():
    # food_adventure (single), dietary (single+followup), vibe_mix (multi select 2)
    return load_questions(FIXTURES / "valid_questions.json")
