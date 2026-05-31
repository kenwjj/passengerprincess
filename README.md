# Travel Companion Bot — Phase 1 (Onboarding Quiz)

A Telegram bot that runs a short multiple-choice onboarding quiz and saves each
user's travel profile. Phase 1 of the travel companion project (see
`travel-companion-bot-requirements.md`). No LLM yet.

## Setup

Uses [uv](https://docs.astral.sh/uv/) for dependency management. Python 3.12 is
pinned via `.python-version`; uv installs it automatically if missing.

```powershell
uv sync
```

This creates `.venv` and installs all dependencies (including dev tools) from
`pyproject.toml` / `uv.lock`. No manual venv activation needed — prefix commands
with `uv run`.

## Create a bot token

1. In Telegram, message **@BotFather**.
2. Send `/newbot`, choose a name and username.
3. Copy the token it gives you.
4. `Copy-Item .env.example .env` and set `BOT_TOKEN=<your token>`.

`.env` is gitignored — never commit your token.

## Run

```powershell
uv run python -m src.bot
```

Then open your bot in Telegram and send `/start`.

## Commands

- `/start` — take the onboarding quiz (restarts if already taken)
- `/restart` — redo the quiz
- `/profile` — view your saved profile
- `/help` — list commands

## Editing the quiz (no code needed)

Quiz content lives in `src/questions.json`. Each question has an `id`,
`category`, `text`, `type` (`single` or `multi`), and `options`. For a
"pick N" question use `"type": "multi"` with `"select": N`. An option can carry
a `"followup": "<prompt>"` to ask for free-text after it's chosen (e.g.
allergies). The bot validates this file on startup and refuses to run if it's
malformed.

## Tests

```powershell
uv run pytest
```

Pure logic (question loading, quiz engine, profile rendering, repositories) is
covered by tests. Telegram handlers are verified manually.
