"""Call Claude Sonnet with the emit_itinerary tool and validate the result.

Network-touching but thin: prompt building, schema, and validation live
elsewhere and are unit-tested. Retry logic is covered with a fake client.
"""

from __future__ import annotations

from src.trip.schema import EMIT_ITINERARY_TOOL, Itinerary, ItineraryError, validate

# Generous headroom so a detailed multi-day (5-7 day) itinerary isn't truncated
# mid-JSON, which would fail validation and waste a retry.
_MAX_TOKENS = 8192


def _extract_itinerary_input(response) -> dict | None:
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "emit_itinerary":
            return block.input
    return None


def generate_itinerary(
    client,
    model: str,
    *,
    system: str,
    user: str,
    start_date: str,
    end_date: str,
    max_retries: int = 1,
) -> Itinerary:
    """Generate + validate an itinerary. Retries up to max_retries times on a
    missing tool call or validation failure."""
    last_error: ItineraryError | None = None
    for _ in range(max_retries + 1):
        response = client.messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            tools=[EMIT_ITINERARY_TOOL],
            tool_choice={"type": "tool", "name": "emit_itinerary"},
        )
        raw = _extract_itinerary_input(response)
        if raw is None:
            last_error = ItineraryError("model did not call emit_itinerary")
            continue
        try:
            return validate(raw, start_date=start_date, end_date=end_date)
        except ItineraryError as exc:
            last_error = exc
    raise last_error if last_error else ItineraryError("generation failed")
