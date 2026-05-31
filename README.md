# Travel Companion Bot — Phases 1–2A (Quiz + Itinerary Generator)

A Telegram bot that runs a short multiple-choice onboarding quiz, saves each
user's travel profile, and generates personalized day-by-day itineraries via the
Anthropic API. Phases 1–2A of the travel companion project (see
`travel-companion-bot-requirements.md`).

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
5. Get an Anthropic API key from https://console.anthropic.com and set `ANTHROPIC_API_KEY=<your key>` in `.env`.

`.env` is gitignored — never commit your token. The bot fails fast on startup if `ANTHROPIC_API_KEY` is missing.

## Run

```powershell
uv run python -m src.bot
```

Then open your bot in Telegram and send `/start`.

## Commands

- `/start` — take the onboarding quiz (restarts if already taken)
- `/restart` — redo the quiz
- `/profile` — view your saved profile
- `/newtrip` — plan a new trip (DM): destination → dates → activity → pick party → generate
- `/trips` — list your trips; tap one to re-view it (or generate a not-yet-generated one)
- `/help` — list commands

## Editing the quiz (no code needed)

Quiz content lives in `src/questions.json`. Each question has an `id`,
`category`, `text`, `type` (`single` or `multi`), and `options`. For a
"pick N" question use `"type": "multi"` with `"select": N`. An option can carry
a `"followup": "<prompt>"` to ask for free-text after it's chosen (e.g.
allergies). The bot validates this file on startup and refuses to run if it's
malformed.

## Itinerary generation (Phase 2A)

`/newtrip` runs a guided wizard in a DM with the bot:
1. **Destination** (free text, e.g. "Jeju")
2. **Dates** — natural language ("Oct 24-28", "2026-10-24 to 2026-10-28"), parsed with `python-dateutil`
3. **Activity** — 🚲 Cycling / 🚗 Self-drive / 🧭 General
4. **Party** — pick from members who have completed the quiz (you're always included)
5. **Generate** — Claude Sonnet returns a day-by-day plan tuned to all party profiles

The plan is saved and re-viewable via `/trips`. Note: distances and times are
**LLM estimates** in this phase — real cycling distances and daylight checks
arrive in a later update.

### Manual smoke test

The unit suite covers all pure logic; the live Telegram + LLM path is verified by
hand (needs `BOT_TOKEN` + `ANTHROPIC_API_KEY` set). Run `uv run python -m src.bot`, then in a DM with the bot:

1. Two accounts each `/start` → finish the quiz (so ≥2 completed profiles exist).
2. `/newtrip` → "Jeju" → "Oct 24-28" → tap 🚲 Cycling → toggle the other member on → Done → confirm screen shows Jeju, the dates, 5 days, both names.
3. Tap ✨ Generate → "planning…" → a lead message + 5 day messages arrive, HTML renders cleanly, days reference the members' actual preferences.
4. `/trips` → lists the trip → tapping it re-renders the saved itinerary.
5. Restart the bot process → `/trips` → trip still there and viewable (persistence).
6. `/newtrip` as a user who never finished the quiz → blocked with "finish your profile first".
7. Tap a stale button from an old message → friendly toast, no hung spinner.

## Tests

```powershell
uv run pytest
```

Pure logic (question loading, quiz engine, profile rendering, repositories) is
covered by tests. Telegram handlers are verified manually.
