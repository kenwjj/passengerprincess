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


ITINERARY_MODEL = os.environ.get("ITINERARY_MODEL", "claude-sonnet-4-6")

# Hardcoded for Phase 2A: late-October sunset in Jeju (KST, HH:MM). Real
# per-location daylight lands in slice 2B (sunrise-sunset.org).
DEFAULT_SUNSET = "17:45"


def get_anthropic_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to your .env file."
        )
    return key
