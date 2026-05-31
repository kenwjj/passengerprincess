"""Single place that constructs the Anthropic SDK client."""

from __future__ import annotations

import anthropic


def build_client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key)
