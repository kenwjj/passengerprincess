"""Environment + path configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_PATH = Path(__file__).resolve().parent / "questions.json"
DB_PATH = ROOT / "quiz.db"


def get_bot_token() -> str:
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "BOT_TOKEN is not set. Copy .env.example to .env and add your BotFather token."
        )
    return token
