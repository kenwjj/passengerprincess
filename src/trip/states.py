"""aiogram FSM states for the /newtrip wizard."""

from aiogram.fsm.state import State, StatesGroup


class NewTrip(StatesGroup):
    destination = State()
    dates = State()
    activity = State()
    party = State()
    confirm = State()
