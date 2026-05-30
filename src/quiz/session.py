"""Helpers over aiogram FSMContext for per-user quiz progress.

FSM data keys:
  selections   -> list[str]  in-progress option ids for the current multi question
  followup_qid -> str        question id awaiting a free-text followup
"""

from __future__ import annotations

from aiogram.fsm.context import FSMContext


async def get_selections(state: FSMContext) -> list[str]:
    data = await state.get_data()
    return list(data.get("selections", []))


async def set_selections(state: FSMContext, selections: list[str]) -> None:
    await state.update_data(selections=selections)


async def clear_selections(state: FSMContext) -> None:
    await state.update_data(selections=[])


async def set_followup_qid(state: FSMContext, qid: str) -> None:
    await state.update_data(followup_qid=qid)


async def get_followup_qid(state: FSMContext) -> str | None:
    data = await state.get_data()
    return data.get("followup_qid")
