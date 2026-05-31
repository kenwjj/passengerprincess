"""Entrypoint: build the bot, load data, start long-polling."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from src.config import QUESTIONS_PATH, get_bot_token
from src.db import connect
from src.questions import load_questions
from src.quiz.handlers import router

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    token = get_bot_token()
    questions = load_questions(QUESTIONS_PATH)  # fail fast if content invalid
    conn = connect()

    bot = Bot(token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    logging.info("Loaded %d questions. Starting long-polling…", len(questions))
    try:
        # conn + questions are injected into handlers as kwargs (workflow data).
        await dp.start_polling(bot, conn=conn, questions=questions)
    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
