"""LLM provider interface (spec section 8.1).

Providers implement two primitives. Everything clinical-facing is built on top of them
in `app.llm.tasks`, which also owns the deterministic mock behaviour and fallbacks.
`tier` lets a provider route latency-sensitive calls ("fast") and quality-sensitive
calls ("quality", e.g. medical translation) to different models.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

Tier = Literal["fast", "quality"]


class LLMError(Exception):
    """Transport/HTTP failure. Callers fall back to mock behaviour and log it."""


class LLMRefusal(Exception):
    """The model refused or hit max_tokens. Callers must not use the output: they fall
    back to approved template text and open an `llm_refusal` escalation."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class LLMProvider(Protocol):
    name: str

    def complete_json(self, system: str, user: str, schema: dict[str, Any], tier: Tier = "quality") -> dict[str, Any]: ...

    def complete_text(self, system: str, user: str, tier: Tier = "quality") -> str: ...
