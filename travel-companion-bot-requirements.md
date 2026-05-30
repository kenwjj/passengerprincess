# Travel Companion Bot — Requirements & Phased Build Plan

## Project context

**What:** A Telegram-first travel companion bot, with a Mini App for richer views (maps, itinerary screens), built as a personal tool for self-drive and cycling trips. The bot learns the user via a short multiple-choice onboarding quiz, proposes itineraries tuned to those preferences, accounts for drive/ride time and daylight, ingests bookings via forwarded emails/photos parsed by an LLM, nudges the user proactively before the trip, and during the trip suggests reschedules when weather or timing changes the plan.

**Why:** Existing tools (Wanderlog, TripIt, Roadtrippers) handle itinerary + map well but none combine daylight-awareness, weather-awareness, proactive nudges, persistent preference memory, and a chat-first interface. The wedge is the proactive in-trip companion that knows you.

**Who it's for (v1):** The builder, his wife, and two friends going on a cycling trip in Jeju in late October 2026. This is a personal tool and a vibe-coding learning project, not a startup.

**Killer demo:** During the trip, the bot proactively thinks ahead, plans, and reschedules the itinerary when something crops up or circumstances change — and because it knows the user, its suggestions feel personal.

## Target trip (the deadline)

- **Destination:** Jeju Island, South Korea
- **Activity:** Cycling (likely the Jeju Fantasy Bike Path / 환상자전거길, ~234 km)
- **Dates:** Late October 2026
- **Party:** 4 people (builder, wife, 2 friends)
- **Constraints to model:** October sunset in Jeju ~5:45pm, variable weather, bike-segment distances and times (not driving times), stamp stations along the certified route

## Tech stack (proposed, change as you learn)

- **Bot platform:** Telegram (Bot API), built around BotFather token
- **Backend:** Node.js or Python (whichever the builder is more comfortable with)
- **Database:** SQLite for v1 — do not over-engineer
- **LLM:** Anthropic API — Claude Sonnet for itinerary generation, Claude Haiku for cheap structured extraction (booking parsing)
- **Maps:** Google Maps Directions API or Mapbox for routing; Mini App webview for visual map
- **Daylight:** sunrise-sunset.org free API
- **Weather:** Open-Meteo or similar free forecast API
- **Hosting:** Whatever's cheap and works — Railway, Fly.io, or a single VPS

## Roles

- **Builder:** All coding, backend, prompt engineering, integrations
- **Wife:** UI/UX (bot message formatting, Mini App screens, onboarding flow), bot persona/tone/copywriting, marketing if it ever becomes a thing
- **Cadence:** Recurring weekly or biweekly pair session — builder drives code, wife drives design/copy. Don't let this devolve into solo evening work; the partnership is a meta-goal.

## Out of scope (forever, or at least for now)

- Bookings/payments inside the bot — use deep links to Booking.com, Airbnb, etc.
- Group trip collaboration features beyond a shared group chat
- WhatsApp, iMessage, or any non-Telegram interface
- A full custom map UI beyond a basic Mini App view
- Trip journaling, photo albums, post-trip recap
- Creator/influencer trip templates with Instagram/TikTok crossover (was previously "phase 3" — cut cleanly)

---

# Phase 1 — Onboarding quiz bot

**Goal:** A working Telegram bot that runs the quiz, saves answers, and shows them back.
**Target ship date:** End of June 2026 (2–3 weekends)
**Why first:** Smallest possible thing. Teaches the bot loop end-to-end. Gives the wife real design surface (persona, copy, profile card). No LLM yet — keeps complexity low.

## Scope

- Telegram bot registered via BotFather, token stored in env
- `/start` triggers the onboarding quiz
- ~10 questions, each presented with inline keyboard buttons (multiple choice, 3–4 options each)
- Answers stored per Telegram user ID in SQLite
- `/profile` command shows the user's saved profile back as a nicely formatted message
- `/restart` lets a user redo the quiz
- Bot has a name, persona, and consistent tone (wife's call)

## Questionnaire categories (design pass: wife refines copy and options)

1. **Food adventurousness** — e.g., "Your last meal would be?" → ramen / sushi / pizza / burger
2. **Dietary needs** — none / vegetarian / vegan / allergies (specify later)
3. **Drink preference** — coffee / wine / beer / cocktails / none
4. **Pace** — cram everything in / one big thing per day / zero plans is the dream
5. **Crowds** — bucket-list spots / hidden gems / doesn't matter
6. **Vibe mix** — nature / culture / food / nightlife (pick top 2)
7. **Body clock** — morning person / night owl / flexible
8. **Budget tier** — backpacker / mid / splurge / mixed
9. **Physical effort tolerance** — all-day hike / moderate / minimal
10. **Spontaneity** — locked plans / loose framework / pure vibes

## Acceptance criteria

- Both builder and wife can run `/start`, answer all 10 questions, and see their profile
- Profile persists across bot restarts
- The two friends can also onboard themselves
- The quiz feels fun, not like a tax return — takes ≤ 2 minutes

---

# Phase 2 — Itinerary generator

**Goal:** Tell the bot "Jeju, Oct 24–28, cycling" and get back a day-by-day plan tuned to all profiles.
**Target ship date:** End of August 2026 (4–6 weekends)
**Why second:** This is the largest learning surface — prompt engineering, structured LLM output, Mini App basics, map APIs.

## Scope

- New command: `/newtrip` walks user through destination, dates, activity type, party members
- Backend builds an LLM prompt combining: destination, dates, activity, ALL party members' profiles (when multiple users), daylight constraints, and known route data
- LLM (Claude Sonnet) returns structured JSON: per-day stops, suggested arrival/depart times, notes
- For each day, the bot computes and renders:
  - Stops in order
  - Distance + time between stops (Google Maps Directions API, **bike mode for cycling trips**)
  - Sunset time and remaining daylight at each stop
  - Total day distance / time / elevation gain (cycling)
- One Telegram message per day, well-formatted, with a "📍 View map" button → Mini App
- Mini App shows the day's stops on a map (Google Maps or Mapbox)
- User can reply naturally: "make day 3 more chill" / "swap day 2 lunch for something foodie" → re-prompts LLM with the edit context
- Trip saved to DB, retrievable via `/trips`

## Risks and notes

- **Bike times ≠ car times.** Use cycling routing mode. For Jeju, the Fantasy Bike Path has known segments; consider hand-loading a small dataset of certified stamp stations, recommended food stops, and accommodation along the route.
- **LLM output will feel generic at first.** Plan for at least 2 weekends just iterating on the prompt and how profile data is injected. The first 5 outputs will read like "and then visit the famous local market." That is the work.
- **Group profiles are non-trivial.** When 4 people have conflicting preferences (one vegetarian, two coffee, one wine, two early birds, two night owls), how does the bot weight them? For v1, simplest answer: feed all profiles into the prompt and let the LLM negotiate, then let the group iterate in chat.

## Acceptance criteria

- Bot produces a Jeju 5-day cycling itinerary tuned to all 4 profiles
- The plan is visibly better/more personal than what generic ChatGPT outputs from the same inputs
- Each day's stops are reachable in daylight at cycling pace
- Edit-by-chat works: a reply like "less driving on day 3" changes day 3 and only day 3

---

# Phase 3 — Pre-trip nudges + booking parsing

**Goal:** Bot reaches out before the trip, not just when summoned. Plan fills in over time.
**Target ship date:** Late September 2026 (2–3 weekends)

## Scope

- Cron job (or scheduled task) checks for upcoming trips and identifies gaps in the plan (no accommodation booked, no rental bike confirmed, no ferry/flight, etc.)
- Sends nudges at T-30d, T-14d, T-7d, T-1d — content depends on which gaps exist
- Forward an email or upload a photo of a booking → backend extracts text → Claude Haiku parses into `{type, date, location, confirmation_number, notes}`
- Bot always confirms the parsed result in chat before saving: "I read this as: ferry Mokpo → Jeju, Oct 23, 09:00, conf# XYZ — looks right?"
- Confirmed bookings mark the corresponding gap as filled
- Weather forecast check at T-7d gives a heads-up if conditions look rough

## Acceptance criteria

- Forwarding a hotel confirmation to the bot results in the booking being added correctly to the trip
- The trip's "missing pieces" list shrinks as bookings come in
- The bot proactively sends a useful nudge at least once without being asked

---

# Phase 4 — In-trip companion (during the Jeju trip)

**Goal:** The bot is genuinely useful on the ground.
**Target ship date:** Late October 2026 (build minimum upfront, iterate during the trip)

## Scope (intentionally vague — finalize closer to October)

Build only the parts you actually want during the trip. Likely candidates:

- "I'm at stop 2, done" check-in → bot recomputes remaining day vs. remaining daylight, flags risk
- Morning briefing: weather + today's plan + any suggested re-ordering
- `/swap` command or natural-language ask: "it's raining, what should we do" → suggests an alternative
- Restaurant suggestion at meal times based on current Telegram-shared location + group food preferences
- End-of-day "how did it go" check-in that updates preferences (e.g., "we hated the museum" → quietly nudges future suggestions away from museums)

## Critical principle

**Do not pre-build all of Phase 4.** Build a thin version, take it on the trip, and update it on the fly between days. The most valuable learning is discovering what actually matters at km 60 of day 2 with sore legs and a rain forecast — not at a desk in May.

## Acceptance criteria

- At least one moment during the Jeju trip where the bot does something genuinely useful that wouldn't have happened otherwise (e.g., suggests swapping plans because of incoming rain, warns that the next stop is unreachable before sunset)
- All 4 trip members find it worth keeping in the group chat

---

# Phase 5 — Post-trip (November 2026+)

Decide whether this stays a personal tool or becomes something more. Both are fine outcomes. Many great personal tools should stay personal tools.

If it stays personal: clean up, document, use for next trip.
If it becomes more: revisit the original startup-shaped phasing (creator templates, market choice, real onboarding, real auth, real billing).

---

# Operating principles

- **Ship small, soak long.** When Phase 1 is shippable in a weekend, ship it that weekend and live with it for two weeks before starting Phase 2. The bot needs daily-use exposure to teach you what's actually missing.
- **The Telegram group is alpha.** Get the wife and two friends into a Telegram group with the bot from week 1. They become real users from day 1, not at the end.
- **Pair sessions are sacred.** Weekly or biweekly pair-build with the wife. Code + design at the same time. Do not let evenings-alone become the default.
- **Vibe coding loop:** describe the next small thing in natural language to the AI assistant, accept the diff, run it, observe, iterate. Don't try to design the whole system upfront.
- **Kill the backlog mercilessly.** Anything not serving the Jeju trip is suspect. Anything not serving the wedge (proactive + personal + daylight/weather-aware) is double-suspect.

---

# Open questions to revisit during build

- Group preference weighting algorithm (currently: let the LLM negotiate; revisit if it produces bad results)
- How to handle private vs. shared trip data in a group chat — does every member's profile inform the plan, or only the trip creator's?
- How to handle multi-leg / non-English bookings (Korean ferry confirmations, Japanese hotel emails)
- Whether to persist learned preferences automatically or always ask before updating the profile
- What happens after the Jeju trip — does the bot ask "want to plan the next one"?
