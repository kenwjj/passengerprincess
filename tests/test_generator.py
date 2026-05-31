import pytest

from src.trip import generator, schema

START, END = "2026-10-24", "2026-10-24"  # 1 day


def _good_input():
    return {
        "trip_summary": "Nice.",
        "days": [
            {
                "day_number": 1, "date": "2026-10-24", "title": "A",
                "summary": "B", "daylight_note": "C",
                "stops": [{"name": "X", "type": "ride", "note": "Y"}],
            }
        ],
    }


def _bad_input():
    bad = _good_input()
    bad["days"][0]["stops"][0]["type"] = "nope"
    return bad


class _Block:
    def __init__(self, inp):
        self.type, self.name, self.input = "tool_use", "emit_itinerary", inp


class _Resp:
    def __init__(self, inp):
        self.content = [_Block(inp)]


class _SeqClient:
    """Returns a queued payload per create() call; records call count."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.calls = 0
        self.messages = self

    def create(self, **kwargs):
        self.calls += 1
        return _Resp(self._payloads.pop(0))


def test_generate_returns_validated_itinerary():
    client = _SeqClient([_good_input()])
    itin = generator.generate_itinerary(
        client, "sonnet", system="s", user="u", start_date=START, end_date=END
    )
    assert isinstance(itin, schema.Itinerary)
    assert client.calls == 1


def test_generate_retries_once_on_invalid_then_succeeds():
    client = _SeqClient([_bad_input(), _good_input()])
    itin = generator.generate_itinerary(
        client, "sonnet", system="s", user="u", start_date=START, end_date=END
    )
    assert isinstance(itin, schema.Itinerary)
    assert client.calls == 2


def test_generate_raises_after_retries_exhausted():
    client = _SeqClient([_bad_input(), _bad_input()])
    with pytest.raises(schema.ItineraryError):
        generator.generate_itinerary(
            client, "sonnet", system="s", user="u", start_date=START, end_date=END
        )
    assert client.calls == 2


def test_generate_raises_when_model_skips_tool_call():
    class _NoToolResp:
        content = []  # no tool_use block at all

    class _NoToolClient:
        def __init__(self):
            self.calls = 0
            self.messages = self

        def create(self, **kwargs):
            self.calls += 1
            return _NoToolResp()

    client = _NoToolClient()
    with pytest.raises(schema.ItineraryError, match="did not call emit_itinerary"):
        generator.generate_itinerary(
            client, "sonnet", system="s", user="u", start_date=START, end_date=END
        )
    # A missing tool call also triggers the retry, so it exhausts both attempts.
    assert client.calls == 2
