# Phase 2A — Personalized Text Itinerary — Design

**Date:** 2026-05-31
**Status:** Design under review
**Source spec:** `travel-companion-bot-requirements.md` → Phase 2 (sliced)
**Scope:** Slice 2A only. Soak before 2B.

## Why this is a slice, not all of Phase 2

Phase 2 in the requirements spans six subsystems: the `/newtrip` wizard + trip
persistence, LLM itinerary generation, daylight (sunrise-sunset API), routing
(distance/time/elevation via Google Maps, bike mode), a Mini App map view, and
edit-by-chat. That is too large for one spec and violates the project's own
"ship small, soak long" principle. Phase 2 is therefore decomposed:

| Slice | Contains | New external deps |
|---|---|---|
| **2A (this doc)** | `/newtrip` wizard, party assembly, prompt build, Claude Sonnet → structured day plan, text message per day, save trip, `/trips`. Hardcoded sunset constant. | Anthropic API only |
| 2B | sunrise-sunset.org daylight + Google Maps bike-mode distance/time/elevation; geocode stops; feed real numbers back into the prompt → daylight-feasible days. | + Google Maps, sunrise API |
| 2C | Edit-by-chat: natural-language reply re-prompts the LLM, changes only the targeted day. | (none new) |
| 2D | Mini App map view of a day's stops + "📍 View map" button. | + Mini App hosting |

Each later slice gets its own spec → plan → ship → soak cycle.

## Goal

Tell the bot, via a guided `/newtrip` wizard, "Jeju, late October, cycling" and
who's coming, and get back a day-by-day itinerary tuned to **all** party
members' Phase 1 profiles — visibly more personal than what generic ChatGPT
produces from the same inputs. Text only. The plan persists and is retrievable
via `/trips`.

## Decisions (locked)

| Decision | Choice | Rationale |
|---|---|---|
| Slice boundary | 2A only | Ship small; biggest learning surface (prompt eng + structured output) isolated from maps/Mini App |
| Party assembly | DM; creator picks from quiz-completed users (multi-select toggle) | Reuses Phase 1 DM model; no group-chat plumbing yet |
| Route grounding | Trust Claude's own Jeju knowledge | Builder's call. Distances/times are **LLM estimates, explicitly labelled**. Real grounding is 2B. |
| Structured output | Force `emit_itinerary` tool call; tool `input_schema` *is* the day-plan contract | Most reliable structured output; no fragile JSON parsing |
| Storage | Validated itinerary JSON blob on the `trips` row | YAGNI-right for 4 users; regenerate overwrites the blob; 2C can re-emit per day |
| Daylight | Hardcoded Jeju late-Oct sunset constant injected into the prompt; model self-flags tight days in `daylight_note` | No daylight API or code-side math in 2A |
| Group conflicts | Feed all profiles into one prompt, let the LLM negotiate | Per spec's stated v1 answer |
| Dates | Natural-language free text, parsed by **Claude Haiku** structured extraction → ISO `{start,end}`; confirm screen echoes the interpretation | Friendlier than ISO typing; spec earmarks Haiku for cheap extraction; confirm step is the safety net |
| Itinerary model | `claude-sonnet-4-6` (config-swappable) | Spec: Sonnet for itinerary generation |
| Date-parse model | `claude-haiku-4-5-20251001` (config-swappable) | Spec: Haiku for cheap structured extraction |

## Architecture

Extends Phase 1's principle: pure, unit-testable logic separated from network
(`generator.py`) and Telegram (`handlers.py`) wiring. Handlers stay thin —
translate Telegram events into engine/repo/generator calls and render results.

### Stack & dependencies

- Existing: Python 3.11+, `aiogram` 3.x (long-polling, MemoryStorage FSM),
  stdlib `sqlite3`/`json`, `python-dotenv`, `pytest`.
- **New:** `anthropic` SDK. No date-parsing dependency (Haiku handles dates).

### Project structure (additions to Phase 1)

```
src/
  config.py          # + ANTHROPIC_API_KEY, ITINERARY_MODEL, DATE_MODEL, JEJU_SUNSET
  db.py              # + trips, trip_members schema (idempotent, alongside Phase 1 tables)
  llm/
    __init__.py
    client.py        # THIN: build Anthropic client from key; one place that touches the SDK
  repos/
    trips.py         # create trip, add members, save/load itinerary blob, list trips, get trip
  profile/
    summary.py       # PURE: (questions, answers) -> compact text profile for the prompt
  trip/
    __init__.py
    states.py        # aiogram FSM StatesGroup: NewTrip wizard
    session.py       # FSMContext helpers (destination, raw_dates, parsed dates, activity, member picks)
    dates.py         # THIN: Haiku call -> {start_date, end_date}; PURE validation of the result
    wizard.py        # PURE: step definitions, activity options, member-list keyboard data, confirm summary
    prompt.py        # PURE: build system + user prompt from trip inputs + party summaries + sunset
    schema.py        # emit_itinerary input_schema + Itinerary dataclasses + validate(raw) -> Itinerary
    generator.py     # THIN: call Sonnet with the tool, return validated Itinerary (1 retry on invalid)
    render.py        # PURE: Itinerary -> [HTML message per day]; lead message; trips-list render
    handlers.py      # Router: /newtrip wizard, /trips, view-trip + retry callbacks
```

`bot.py` includes the new `trip.handlers.router` and injects the Anthropic
client alongside the existing `conn` + `questions` workflow data.

### Data model (added to existing schema in `db.py`)

```sql
CREATE TABLE IF NOT EXISTS trips (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  creator_id     INTEGER NOT NULL,          -- telegram_user_id
  destination    TEXT    NOT NULL,
  start_date     TEXT    NOT NULL,          -- ISO date (YYYY-MM-DD)
  end_date       TEXT    NOT NULL,          -- ISO date
  activity       TEXT    NOT NULL,          -- 'cycling' | 'self_drive' | 'general'
  itinerary_json TEXT,                      -- NULL until generated; validated blob
  created_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS trip_members (
  trip_id          INTEGER NOT NULL,
  telegram_user_id INTEGER NOT NULL,
  PRIMARY KEY (trip_id, telegram_user_id)
);
```

Member profiles are read **live** from the Phase 1 `answers` table at generation
time — no snapshot copy (YAGNI; a learning tool with 4 users does not need
profile-versioning).

### `/newtrip` wizard flow (DM, FSM)

State lives in aiogram `FSMContext` (per-user, in-memory) during the wizard; the
trip is persisted only at the generate step.

1. `/newtrip` → prompt for **destination** (free text).
2. Prompt for **dates** (free text, e.g. "Oct 24–28"). On submit, call Haiku
   (`trip/dates.py`) to extract `{start_date, end_date}` ISO. If extraction
   fails or yields an invalid/back-to-front range, ask the user to rephrase.
3. **Activity** → inline keyboard: 🚲 Cycling / 🚗 Self-drive / 🧭 General.
4. **Party** → toggle list of users with `completed_at IS NOT NULL`
   (creator auto-included and shown locked). **Done** confirms. (Reuses the
   Phase 1 multi-select toggle + edit-in-place pattern.)
5. **Confirm** → render a summary (destination, interpreted dates + day count,
   activity, party names) with **Generate** and **Start over** buttons.
6. On **Generate**: persist `trips` + `trip_members` rows → send
   "✍️ Planning your trip… (~20s)" → build prompt → call Sonnet with the
   `emit_itinerary` tool → `validate()` → save blob → send the lead message and
   one message per day.

### Commands

- `/newtrip` — start the wizard (DM).
- `/trips` — list this user's trips (destination, dates, day count, generated?);
  one inline button per trip re-renders its saved itinerary. Trips with a NULL
  itinerary show "(not generated — tap to retry)" and the button re-runs
  generation for that trip's stored inputs + members.
- `/help` — updated to mention `/newtrip` and `/trips`.

### LLM prompt (the work)

**System prompt** sets persona/tone (placeholder, wife refines later) and hard
rules: respect **every** party member's profile; explicitly negotiate and name
conflicts (e.g. "two early birds, one night owl — front-loaded the big rides");
plan at cycling pace and aim to finish each day before the given sunset; be
specific and local, **no generic "visit the famous local market" filler**;
return results **only** via the `emit_itinerary` tool.

**User content:** destination; dates with weekday + computed day count; activity;
the sunset constant; and each member's compact profile summary
(`profile/summary.py`). Prompt construction is pure and deterministic given
inputs (`trip/prompt.py`), so it is unit-testable.

> Implementation note: when wiring the SDK, apply the `claude-api` skill's
> guidance, including prompt caching on the static system prompt.

### Itinerary schema (`emit_itinerary` tool `input_schema`)

```
trip_summary: str                     # 1–2 sentences, tuned to the group
days: array of {
  day_number:  int
  date:        str                    # ISO, must fall within [start_date, end_date]
  title:       str                    # e.g. "West coast: Aewol → Hallim"
  summary:     str                    # why this day fits the group
  stops: array of {
    name:   str
    type:   enum 'ride'|'food'|'sight'|'rest'|'accommodation'
    arrive: str|null                  # HH:MM local, model estimate
    depart: str|null
    note:   str                       # personalized reason / tip
  }
  daylight_note: str                  # model's call on finishing before sunset
}
```

`schema.py.validate(raw)` checks structure, the `type` enum, day count vs the
date range, and dates within range; returns typed `Itinerary` dataclasses or
raises. `generator.py` retries once on a validation failure before surfacing a
friendly error. Distances/times throughout are **model estimates**, surfaced as
such in rendering.

### Rendering (`trip/render.py`, pure, HTML-safe)

- **Lead message:** `trip_summary` + party names + a disclaimer:
  *"⏱ Times are estimates for now — real cycling distances & daylight checks are
  coming in a later update."*
- **One message per day:** header `Day N · <date, weekday> · <title>`, the day
  summary, then stops (emoji by `type`, `arrive–depart` if present, name, note),
  and the `daylight_note` as a footer.
- All user/LLM text HTML-escaped (reuse Phase 1 escaping approach).
- `render_trips_list(trips)` for `/trips`.

### Error handling

- Missing `ANTHROPIC_API_KEY` → fail fast at startup (mirrors `BOT_TOKEN`).
- Creator or a picked member has no completed profile → block generation with a
  message naming who still needs to run `/start`.
- Haiku date extraction fails/ambiguous → ask the user to rephrase the dates.
- Sonnet call error/timeout → friendly "couldn't plan right now — try again";
  the `trips` row is kept with `itinerary_json` NULL and is retryable via
  `/trips`.
- Invalid tool output → `validate()` → one retry → friendly failure (row stays
  NULL).
- Stale/duplicate wizard callbacks → answered like Phase 1 (no hung spinner).
- Wizard handlers are async → the "planning…" message is sent immediately and
  one user's slow generation does not block other users.

### Testing (pytest; pure where possible)

- `test_prompt.py` — prompt includes every member summary, sunset, dates (with
  day count), and activity; deterministic for fixed inputs.
- `test_schema.py` — `validate()` accepts a good blob; rejects bad `type`,
  out-of-range dates, wrong day count, missing fields.
- `test_render.py` — day formatting (types, time ranges, daylight footer),
  HTML-safety, multi-day, lead message, trips-list render.
- `test_repos_trips.py` — create trip, add members, save/load blob, list trips
  for a user, get trip (in-memory `:memory:` sqlite).
- `test_wizard.py` — step transitions; activity options; member keyboard data;
  date-result validation (rejects reversed/invalid ranges).
- `test_dates.py` — pure validation of a parsed date result (the Haiku call
  itself is isolated and not unit-tested against the network).
- `generator.py` and `llm/client.py` kept thin; no live-API unit test. Optional
  manual smoke script for end-to-end generation.

## Acceptance criteria (2A subset of the Phase 2 spec)

- A creator can `/newtrip` → pick the 4 party members (all of whom finished the
  quiz) → enter "Jeju" + late-October dates + cycling → and receive a multi-day
  itinerary, one message per day.
- The itinerary visibly reflects the group's profiles (food, pace, body clock,
  effort, vibe) and names at least one real preference trade-off.
- The plan is qualitatively more personal than generic ChatGPT given the same
  inputs (judged by builder + wife during soak).
- The trip persists and re-renders via `/trips` across bot restarts.
- A failed generation leaves a retryable trip, never a hung spinner.

## Out of scope (2A)

Maps/routing APIs, real distance/time/elevation, daylight API (hardcoded
constant only), Mini App + "View map" button, edit-by-chat (2C), group-chat
`/newtrip`, booking parsing, pre-trip nudges, profile-versioning/snapshots,
hosting/deploy.

## Open questions deferred to later slices

- Group preference weighting beyond "let the LLM negotiate" (revisit if 2A soak
  shows bad results).
- Whether `/newtrip` should eventually run in the group chat (2D-ish).
- Real route grounding via a hand-loaded Jeju dataset vs. Google Maps (2B).
- Itinerary model: default `claude-sonnet-4-6`; A/B `claude-haiku-4-5` on the
  same Jeju trip during soak (model is config-swappable) and downgrade if Haiku
  holds up — cost is negligible at 4-user scale, so this is a quality call.
