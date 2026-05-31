"""aiogram Router: the /newtrip wizard, /trips, and view/retry callbacks."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timezone

import anthropic
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.config import DEFAULT_SUNSET, ITINERARY_MODEL
from src.profile.summary import summarize_profile
from src.questions import Question
from src.trip import dates, generator, prompt, render, session, wizard
from src.trip.schema import Itinerary, ItineraryError
from src.trip.states import NewTrip
from src.repos import answers as answers_repo
from src.repos import trips as trips_repo
from src.repos import users as users_repo

logger = logging.getLogger(__name__)
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


def _display_name(row) -> str:
    if row is None:
        return "Traveler"
    return row["first_name"] or (f"@{row['username']}" if row["username"] else "Traveler")


# ---- /newtrip wizard --------------------------------------------------------

@router.message(Command("newtrip"))
async def cmd_newtrip(message: Message, state: FSMContext, conn: sqlite3.Connection) -> None:
    user = users_repo.get_user(conn, message.from_user.id)
    if user is None or user["completed_at"] is None:
        await message.answer("Finish your profile first — run /start, then /newtrip.")
        return
    await state.clear()
    await state.set_state(NewTrip.destination)
    await message.answer("✈️ New trip! Where are we going?")


@router.message(NewTrip.destination, F.text)
async def on_destination(message: Message, state: FSMContext) -> None:
    await session.set_field(state, destination=message.text.strip())
    await state.set_state(NewTrip.dates)
    await message.answer("📅 When? e.g. \"Oct 24-28\" or \"24 to 28 October\".")


@router.message(NewTrip.dates, F.text)
async def on_dates(message: Message, state: FSMContext) -> None:
    today = datetime.now(timezone.utc).date()
    try:
        # dateutil parsing is fast + synchronous — no thread offload needed.
        start, end = dates.parse_date_range(message.text.strip(), reference=today)
    except dates.DateParseError:
        await message.answer("Couldn't read those dates — try \"Oct 24-28\".")
        return
    await session.set_field(state, start_date=start, end_date=end)
    await state.set_state(NewTrip.activity)
    await message.answer(
        f"Got it: {start} → {end}. What kind of trip?",
        reply_markup=_markup(wizard.activity_keyboard()),
    )


@router.callback_query(NewTrip.activity, F.data.startswith("act:"))
async def on_activity(
    cb: CallbackQuery, state: FSMContext, conn: sqlite3.Connection
) -> None:
    activity = cb.data.split(":", 1)[1]
    await session.set_field(state, activity=activity)
    creator_id = cb.from_user.id
    await session.set_member_ids(state, [creator_id])
    await state.set_state(NewTrip.party)
    users = users_repo.list_completed_users(conn)
    await cb.message.answer(
        "👥 Who's coming? Tap to add, then Done.",
        reply_markup=_markup(wizard.member_keyboard(users, [creator_id], creator_id)),
    )
    await cb.answer()


@router.callback_query(NewTrip.party, F.data.startswith("mem:"))
async def on_member_toggle(
    cb: CallbackQuery, state: FSMContext, conn: sqlite3.Connection
) -> None:
    uid = int(cb.data.split(":", 1)[1])
    creator_id = cb.from_user.id
    current = await session.get_member_ids(state)
    updated = wizard.toggle_member(current, uid, locked=creator_id)
    if updated != current:
        await session.set_member_ids(state, updated)
        users = users_repo.list_completed_users(conn)
        await cb.message.edit_reply_markup(
            reply_markup=_markup(wizard.member_keyboard(users, updated, creator_id))
        )
    await cb.answer()


@router.callback_query(NewTrip.party, F.data == "memdone")
async def on_party_done(
    cb: CallbackQuery, state: FSMContext, conn: sqlite3.Connection
) -> None:
    member_ids = await session.get_member_ids(state)
    data = await state.get_data()
    names = [_display_name(users_repo.get_user(conn, uid)) for uid in member_ids]
    summary = wizard.confirm_summary(
        destination=data["destination"], start_date=data["start_date"],
        end_date=data["end_date"], activity=data["activity"], member_names=names,
    )
    await state.set_state(NewTrip.confirm)
    await cb.message.answer(
        summary,
        parse_mode="HTML",
        reply_markup=_markup([[("✨ Generate", "gen"), ("↩️ Start over", "restart")]]),
    )
    await cb.answer()


@router.callback_query(NewTrip.confirm, F.data == "restart")
async def on_restart(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(NewTrip.destination)
    await cb.message.answer("Okay, starting over. Where are we going?")
    await cb.answer()


@router.callback_query(NewTrip.confirm, F.data == "gen")
async def on_generate(
    cb: CallbackQuery,
    state: FSMContext,
    conn: sqlite3.Connection,
    questions: list[Question],
    anthro: anthropic.Anthropic,
) -> None:
    data = await state.get_data()
    member_ids = await session.get_member_ids(state)
    await cb.answer()
    await state.clear()

    trip_id = trips_repo.create_trip(
        conn, creator_id=cb.from_user.id, destination=data["destination"],
        start_date=data["start_date"], end_date=data["end_date"],
        activity=data["activity"], now=_now(),
    )
    for uid in member_ids:
        trips_repo.add_member(conn, trip_id, uid)

    await cb.message.answer("✍️ Planning your trip… (~20s)")
    await _generate_and_send(cb.message, conn, questions, anthro, trip_id)


@router.message(NewTrip.dates)
@router.message(NewTrip.destination)
async def wizard_expects_text(message: Message) -> None:
    await message.answer("Type your answer as text, please.")


# ---- /trips + view/retry ----------------------------------------------------

@router.message(Command("trips"))
async def cmd_trips(message: Message, conn: sqlite3.Connection) -> None:
    rows = trips_repo.list_trips_for_user(conn, message.from_user.id)
    kb = [[(f"View #{r['id']} · {r['destination']}", f"view:{r['id']}")] for r in rows]
    await message.answer(
        render.render_trips_list(rows),
        parse_mode="HTML",
        reply_markup=_markup(kb) if kb else None,
    )


@router.callback_query(F.data.startswith("view:"))
async def on_view_trip(
    cb: CallbackQuery, conn: sqlite3.Connection
) -> None:
    trip_id = int(cb.data.split(":", 1)[1])
    trip = trips_repo.get_trip(conn, trip_id)
    if trip is None:
        await cb.answer("That trip is gone.")
        return
    if not trip["itinerary_json"]:
        await cb.message.answer(
            "That trip isn't generated yet.",
            reply_markup=_markup([[("🔁 Generate now", f"retry:{trip_id}")]]),
        )
        await cb.answer()
        return
    itin = Itinerary.from_dict(json.loads(trip["itinerary_json"]))
    names = _member_names(conn, trip_id)
    for msg in render.render_itinerary(itin, names):
        await cb.message.answer(msg, parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("retry:"))
async def on_retry_trip(
    cb: CallbackQuery,
    conn: sqlite3.Connection,
    questions: list[Question],
    anthro: anthropic.Anthropic,
) -> None:
    trip_id = int(cb.data.split(":", 1)[1])
    await cb.answer()
    await cb.message.answer("✍️ Planning your trip… (~20s)")
    await _generate_and_send(cb.message, conn, questions, anthro, trip_id)


@router.callback_query()
async def stale_trip_callback(cb: CallbackQuery) -> None:
    # trip_router is included last, so this is the global catch-all for any
    # callback no handler (quiz or trip) claimed — keeps the spinner from hanging.
    await cb.answer("That button's no longer active — /trips or /newtrip.")


@router.message()
async def trip_fallback(message: Message) -> None:
    # Global message catch-all (trip_router is last). Replaces the quiz router's
    # former bare fallback, which would otherwise shadow the wizard's text steps.
    await message.answer("Tap the buttons above, or use /start or /newtrip.")


# ---- shared generation path -------------------------------------------------

def _member_names(conn: sqlite3.Connection, trip_id: int) -> list[str]:
    return [_display_name(users_repo.get_user(conn, uid))
            for uid in trips_repo.get_members(conn, trip_id)]



async def _generate_and_send(
    target: Message,
    conn: sqlite3.Connection,
    questions: list[Question],
    anthro: anthropic.Anthropic,
    trip_id: int,
) -> None:
    trip = trips_repo.get_trip(conn, trip_id)
    if trip is None:
        await target.answer("😕 That trip no longer exists.")
        return
    member_ids = trips_repo.get_members(conn, trip_id)
    # All SQLite access stays on the event-loop thread (connection is
    # check_same_thread=True). Build the prompt here, then offload ONLY the
    # blocking Anthropic call to a worker thread.
    summaries = []
    for uid in member_ids:
        row = users_repo.get_user(conn, uid)
        answers = answers_repo.get_answers(conn, uid)
        summaries.append(f"{_display_name(row)}: {summarize_profile(questions, answers)}")
    user_prompt = prompt.build_user_prompt(
        destination=trip["destination"], start_date=trip["start_date"],
        end_date=trip["end_date"], activity=trip["activity"],
        sunset=DEFAULT_SUNSET, member_summaries=summaries,
    )
    try:
        itin = await asyncio.to_thread(
            generator.generate_itinerary,
            anthro, ITINERARY_MODEL,
            system=prompt.build_system_prompt(), user=user_prompt,
            start_date=trip["start_date"], end_date=trip["end_date"],
        )
    except ItineraryError as exc:
        logger.warning("itinerary validation failed for trip %s: %s", trip_id, exc)
        await target.answer("😕 Couldn't plan that right now. Try again from /trips.")
        return
    except Exception:  # network/transport/SDK errors — keep the trip retryable (NULL itinerary)
        logger.exception("itinerary generation failed for trip %s", trip_id)
        await target.answer("😕 Couldn't plan that right now. Try again from /trips.")
        return
    trips_repo.save_itinerary(
        conn, trip_id, json.dumps(itin_to_dict(itin), ensure_ascii=False)
    )
    names = _member_names(conn, trip_id)
    for msg in render.render_itinerary(itin, names):
        await target.answer(msg, parse_mode="HTML")


def itin_to_dict(itin: Itinerary) -> dict:
    return {
        "trip_summary": itin.trip_summary,
        "days": [
            {
                "day_number": d.day_number, "date": d.date, "title": d.title,
                "summary": d.summary, "daylight_note": d.daylight_note,
                "stops": [
                    {"name": s.name, "type": s.type, "arrive": s.arrive,
                     "depart": s.depart, "note": s.note}
                    for s in d.stops
                ],
            }
            for d in itin.days
        ],
    }
