"""aiogram Router: quiz commands, option callbacks, and followup text."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.profile.render import render_profile
from src.questions import Question
from src.quiz import engine, session
from src.quiz.states import Quiz
from src.repos import answers as answers_repo
from src.repos import users as users_repo

router = Router()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _markup(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=data) for label, data in row]
            for row in rows
        ]
    )


async def _send_next_or_finish(
    target: Message,
    state: FSMContext,
    conn: sqlite3.Connection,
    questions: list[Question],
    user_id: int,
) -> None:
    answered = set(answers_repo.get_answers(conn, user_id))
    q = engine.next_question(questions, answered)
    if q is None:
        users_repo.set_completed_at(conn, user_id, when=_now())
        await state.clear()
        await target.answer("🎉 All done! Here's your profile:")
        answers = answers_repo.get_answers(conn, user_id)
        await target.answer(
            render_profile(questions, answers, is_complete=True), parse_mode="HTML"
        )
        return

    await session.clear_selections(state)
    await state.set_state(Quiz.answering)
    rows = engine.build_keyboard(q, selections=[])
    await target.answer(q.text, reply_markup=_markup(rows))


@router.message(Command("start", "restart"))
async def cmd_start(
    message: Message,
    state: FSMContext,
    conn: sqlite3.Connection,
    questions: list[Question],
) -> None:
    user = message.from_user
    users_repo.upsert_user(
        conn, user.id, username=user.username, first_name=user.first_name, now=_now()
    )
    answers_repo.clear_answers(conn, user.id)
    await state.clear()
    await message.answer("Let's build your travel profile! A few quick taps. 🧭")
    await _send_next_or_finish(message, state, conn, questions, user.id)


@router.message(Command("profile"))
async def cmd_profile(
    message: Message,
    conn: sqlite3.Connection,
    questions: list[Question],
) -> None:
    user_row = users_repo.get_user(conn, message.from_user.id)
    if user_row is None:
        await message.answer("No profile yet — run /start to begin.")
        return
    answers = answers_repo.get_answers(conn, message.from_user.id)
    is_complete = user_row["completed_at"] is not None
    await message.answer(
        render_profile(questions, answers, is_complete=is_complete), parse_mode="HTML"
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "I'm your travel companion (in training).\n"
        "/start — take the onboarding quiz\n"
        "/restart — redo the quiz\n"
        "/profile — see your saved profile"
    )


@router.callback_query(Quiz.answering, F.data.startswith("q:"))
async def on_option(
    cb: CallbackQuery,
    state: FSMContext,
    conn: sqlite3.Connection,
    questions: list[Question],
) -> None:
    _, qid, oid = engine.parse_callback(cb.data)
    question = engine.find_question(questions, qid)
    if question is None or engine.find_option(question, oid) is None:
        await cb.answer("That option expired — /restart to redo.")
        return

    if question.type == "single":
        followup = engine.option_followup(question, oid)
        if followup:
            await session.set_followup_qid(state, qid)
            await state.set_state(Quiz.awaiting_followup)
            await cb.message.answer(followup)
            await cb.answer()
            return
        answers_repo.upsert_answer(conn, cb.from_user.id, qid, oid, now=_now())
        await cb.answer("Saved ✅")
        await _send_next_or_finish(cb.message, state, conn, questions, cb.from_user.id)
        return

    # multi: toggle, re-render in place.
    selections = await session.get_selections(state)
    selections = engine.toggle_selection(selections, oid, question.select)
    await session.set_selections(state, selections)
    rows = engine.build_keyboard(question, selections=selections)
    await cb.message.edit_reply_markup(reply_markup=_markup(rows))
    await cb.answer()


@router.callback_query(Quiz.answering, F.data.startswith("done:"))
async def on_done(
    cb: CallbackQuery,
    state: FSMContext,
    conn: sqlite3.Connection,
    questions: list[Question],
) -> None:
    _, qid, _oid = engine.parse_callback(cb.data)
    question = engine.find_question(questions, qid)
    selections = await session.get_selections(state)
    if question is None or not engine.is_selection_complete(selections, question.select):
        needed = question.select if question else "?"
        await cb.answer(f"Pick exactly {needed}.", show_alert=False)
        return
    answers_repo.upsert_answer(
        conn, cb.from_user.id, qid, json.dumps(selections), now=_now()
    )
    await cb.answer("Saved ✅")
    await _send_next_or_finish(cb.message, state, conn, questions, cb.from_user.id)


@router.message(Quiz.awaiting_followup, F.text)
async def on_followup_text(
    message: Message,
    state: FSMContext,
    conn: sqlite3.Connection,
    questions: list[Question],
) -> None:
    qid = await session.get_followup_qid(state)
    if qid is None:
        await message.answer("Something got out of sync — /restart to redo.")
        return
    answers_repo.upsert_answer(
        conn, message.from_user.id, qid, message.text.strip(), now=_now()
    )
    await _send_next_or_finish(message, state, conn, questions, message.from_user.id)


@router.message()
async def fallback(message: Message) -> None:
    await message.answer("Tap the buttons above, or use /start to (re)take the quiz.")
