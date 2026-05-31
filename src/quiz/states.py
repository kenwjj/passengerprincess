"""aiogram FSM states for the onboarding quiz."""

from aiogram.fsm.state import State, StatesGroup


class Quiz(StatesGroup):
    answering = State()          # showing questions, awaiting button taps
    awaiting_followup = State()  # awaiting a free-text reply (e.g. allergies)
