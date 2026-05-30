# Phase 1 — Onboarding Quiz Bot — Design

**Date:** 2026-05-30
**Status:** Approved (design); spec under review
**Source spec:** `travel-companion-bot-requirements.md` → Phase 1
**Scope:** Phase 1 only. Soak before Phase 2.

## Goal

A working Telegram bot that runs a ~10-question multiple-choice onboarding quiz,
saves answers per Telegram user in SQLite, and shows them back via `/profile`.
No LLM. Smallest end-to-end slice that teaches the bot loop and gives the wife a
real design/copy surface.

## Decisions (locked)

| Decision | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Builder preference |
| Telegram library | python-telegram-bot v21+ (async) | Builder choice; most tutorials/docs |
| Quiz location | DM with bot | Clean per-user state; group chat reserved for trip use later |
| Bot token | Create new via BotFather | None exists yet |
| Question source | `questions.json` (git-tracked) | Wife edits copy/options without code or DB migration |
| Answer storage | Key-value table | Add/remove questions with zero migration |
| Quiz state model | Restart on `/start` | Any `/start` begins fresh from Q1; simple state |
| Multi-select (Q6 "pick top 2") | Generic select-N type | Toggle options + Done button; reusable |
| Free text (Q2 allergies) | Option-level `followup` prompt | Captures real allergy data; one free-text step |
| Updates transport | Long-polling | No public URL/HTTPS; runs from laptop |
| Hosting | Local run for Phase 1 | Deferred to a later phase; 4 known users |
| Persona/name | Placeholder copy | Wife refines tone/name in a pair session |
| Database | SQLite via stdlib `sqlite3` | 4 users → instant queries; no ORM, no async-DB dep |
| LLM | None | Spec: Phase 1 has no LLM |

## Architecture

### Stack & dependencies

- Python 3.11+
- `python-telegram-bot` v21+ (async `Application`, `run_polling`)
- `python-dotenv` (env loading)
- stdlib `sqlite3`, `json`
- Dev: `pytest`

### Project structure

```
src/
  bot.py              # entry: load env, build Application, register handlers, run_polling
  config.py           # env loading (BOT_TOKEN), file paths
  questions.py        # load + validate questions.json
  questions.json      # quiz content (wife edits this)
  db.py               # sqlite connection + schema init (idempotent)
  repos/
    users.py          # upsert user, get user, set completed_at
    answers.py        # upsert answer, get all for user, clear user
  quiz/
    engine.py         # PURE logic: next question, build keyboard markup data,
                      #   validate select-N, detect followup
    session.py        # context.user_data helpers (current index, partial multi picks, pending followup)
    handlers.py       # /start, /restart, /profile, /help, quiz callback, followup text handler
  profile/
    render.py         # PURE: format answers + questions -> profile message text
tests/
  test_engine.py
  test_render.py
  test_repos.py
.env.example          # BOT_TOKEN=
.gitignore            # .env, *.db, __pycache__/, .pytest_cache/
README.md             # BotFather setup + run instructions
```

Design principle: pure logic (`engine.py`, `render.py`, `questions.py` validation)
is separated from Telegram wiring (`handlers.py`) so it is unit-testable without a
live bot. Handlers stay thin — they translate Telegram events into engine/repo
calls and render results.

### Data model (SQLite)

```sql
CREATE TABLE IF NOT EXISTS users (
  telegram_user_id INTEGER PRIMARY KEY,
  username          TEXT,
  first_name        TEXT,
  created_at        TEXT NOT NULL,
  completed_at      TEXT            -- NULL until quiz finished
);

CREATE TABLE IF NOT EXISTS answers (
  telegram_user_id INTEGER NOT NULL,
  question_id      TEXT    NOT NULL,
  value            TEXT    NOT NULL, -- single: option id; multi: JSON array; followup: free text
  answered_at      TEXT    NOT NULL,
  PRIMARY KEY (telegram_user_id, question_id)  -- upsert on re-answer
);
```

No question schema in the DB. Questions live in `questions.json`; answers are
keyed by `question_id`. Adding/removing/editing questions needs no migration.

### questions.json format

A JSON array of question objects, presented in array order.

```json
[
  {
    "id": "food_adventure",
    "category": "Food adventurousness",
    "type": "single",
    "text": "Your last meal on earth would be?",
    "options": [
      {"id": "ramen",  "label": "🍜 Ramen"},
      {"id": "sushi",  "label": "🍣 Sushi"},
      {"id": "pizza",  "label": "🍕 Pizza"},
      {"id": "burger", "label": "🍔 Burger"}
    ]
  },
  {
    "id": "dietary",
    "category": "Dietary needs",
    "type": "single",
    "text": "Anything we should know about food?",
    "options": [
      {"id": "none",       "label": "No restrictions"},
      {"id": "vegetarian", "label": "Vegetarian"},
      {"id": "vegan",      "label": "Vegan"},
      {"id": "allergies",  "label": "Allergies",
       "followup": "Type your allergies, separated by commas:"}
    ]
  },
  {
    "id": "vibe_mix",
    "category": "Vibe mix",
    "type": "multi",
    "select": 2,
    "text": "Pick your top 2 trip vibes:",
    "options": [
      {"id": "nature",    "label": "🌿 Nature"},
      {"id": "culture",   "label": "🏛 Culture"},
      {"id": "food",      "label": "🍴 Food"},
      {"id": "nightlife", "label": "🌃 Nightlife"}
    ]
  }
]
```

Question types (field-driven):

- `single` — one tap selects, stores option id, advances.
- `multi` with `select: N` — tap to toggle (shows ✓), **Done** button confirms;
  Done accepted only at exactly N selections; stores JSON array of option ids.
- Any option may carry `followup: "<prompt>"` — choosing it sends the prompt and
  stores the user's next text message as the answer value.

**Validation on load** (fail fast at startup): non-empty array; unique question
ids; each question has `id`, `category`, `text`, `type`, non-empty `options`;
option ids unique within a question; `multi` has integer `select` with
`1 ≤ select ≤ len(options)`.

All 10 spec questions are expressible in this format. (Spec categories: food
adventurousness, dietary needs, drink preference, pace, crowds, vibe mix [multi
select 2], body clock, budget tier, physical effort tolerance, spontaneity.)

### Quiz flow

State during an active quiz lives in `context.user_data` (per-user, in-memory):
current question index, partial multi-select picks, and a pending-followup flag.

1. `/start` (or `/restart`): upsert user; **clear that user's prior answers** and
   reset `completed_at` to NULL; reset `user_data`; render Q1.
2. **single**: inline keyboard, one button per option (callback data encodes
   question id + option id). Tap → upsert answer → render next.
3. **multi (select-N)**: each option button toggles; selected options render with
   a ✓ and the keyboard is re-rendered in place (`edit_message_reply_markup`). A
   **Done** button stores the JSON array when exactly N are picked (otherwise a
   brief "pick exactly N" answer-callback toast). Then render next.
4. **followup**: when an option with `followup` is tapped, store the option id,
   send the followup prompt, set pending-followup in `user_data`. The next text
   message (caught by a gated `MessageHandler`) is stored as the followup value,
   then advance.
5. After the last question: set `users.completed_at`, send a completion message,
   then render the profile.
6. Bot restart mid-quiz loses in-memory `user_data` → the user re-runs `/start`.
   Acceptable given the restart-on-/start decision. **Completed answers persist
   in SQLite across bot restarts.**

### Commands

- `/start` — begin (or restart) the quiz; clears existing answers.
- `/restart` — explicit alias for `/start`.
- `/profile` — render saved profile from DB. If incomplete, show partial answers
  plus "Run /start to finish."
- `/help` — short blurb (placeholder persona/tone).

### Error handling

- Missing/empty `BOT_TOKEN` → clear startup error, exit.
- Invalid `questions.json` → fail fast at startup with the specific validation error.
- Stale/duplicate button taps (e.g. tapping an old message's button) →
  `answer_callback_query` no-op toast; never crash.
- Unexpected text outside a pending followup → gentle "use the buttons or /start" reply.
- All handlers wrapped so an exception answers the callback/ message gracefully
  rather than leaving the user hanging.

### Testing (pytest)

- `test_engine.py` — next-question selection from answered set; select-N toggle &
  validation; followup detection; `questions.json` schema validation (valid +
  invalid fixtures). Pure, no Telegram.
- `test_render.py` — profile formatting from sample answers + question config,
  including multi-select and free-text values, and the incomplete-profile case.
- `test_repos.py` — against in-memory SQLite (`:memory:`): user upsert; answer
  upsert overwrites on re-answer; clear-user removes answers and resets completion.
- Telegram handlers stay thin; no live-bot integration tests in Phase 1.

### Setup / runtime

- `README.md` documents BotFather `/newbot` → obtain token → copy `.env.example`
  to `.env` → set `BOT_TOKEN`.
- `.env` is gitignored; `.env.example` is committed.
- Run locally with long-polling: `python -m src.bot`.
- Persona/name: neutral placeholder copy in `questions.json` and command
  messages; the wife refines tone and the bot's name in a pair session. Copy is
  isolated (questions.json + a small messages module) so changes are non-code.

## Out of scope (Phase 1)

LLM/itinerary/maps; group-chat quiz; per-answer editing UI; webhooks; hosting/
deploy; durable resume-across-restart of an in-progress quiz; analytics.

## Acceptance criteria (from spec)

- Builder and wife can `/start`, answer all 10 questions, and see `/profile`.
- Profile persists across bot restarts.
- The two friends can also onboard themselves.
- The quiz feels fun, not like a tax return — takes ≤ 2 minutes.
