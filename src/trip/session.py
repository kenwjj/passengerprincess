"""Helpers over aiogram FSMContext for /newtrip wizard data.

FSM data keys: destination, start_date, end_date, activity, member_ids (list[int]).
"""

from __future__ import annotations

from aiogram.fsm.context import FSMContext


async def set_field(state: FSMContext, **fields) -> None:
    await state.update_data(**fields)


async def get_field(state: FSMContext, key: str, default=None):
    return (await state.get_data()).get(key, default)


async def get_member_ids(state: FSMContext) -> list[int]:
    return list((await state.get_data()).get("member_ids", []))


async def set_member_ids(state: FSMContext, ids: list[int]) -> None:
    await state.update_data(member_ids=ids)
