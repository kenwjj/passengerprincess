"""Entrypoint: build the bot, load data, start long-polling."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from src.config import QUESTIONS_PATH, get_anthropic_key, get_bot_token
from src.db import connect
from src.llm.client import build_client
from src.questions import load_questions
from src.quiz.handlers import router as quiz_router
from src.trip.handlers import router as trip_router

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    token = get_bot_token()
    anthro = build_client(get_anthropic_key())  # fail fast if key missing
    questions = load_questions(QUESTIONS_PATH)
    conn = connect()

    bot = Bot(token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(quiz_router)
    dp.include_router(trip_router)

    logging.info("Loaded %d questions. Starting long-polling…", len(questions))
    try:
        await dp.start_polling(bot, conn=conn, questions=questions, anthro=anthro)
    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
