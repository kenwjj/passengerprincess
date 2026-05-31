import importlib

import pytest


def test_models_have_defaults(monkeypatch):
    monkeypatch.delenv("ITINERARY_MODEL", raising=False)
    import src.config as config
    importlib.reload(config)
    assert config.ITINERARY_MODEL == "claude-sonnet-4-6"
    assert config.DEFAULT_SUNSET == "17:45"


def test_get_anthropic_key_raises_when_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import src.config as config
    importlib.reload(config)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        config.get_anthropic_key()
