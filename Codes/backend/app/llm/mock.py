"""Deterministic offline provider (the default). It never calls a network.

The *task-level* mock behaviour (fixture translations, keyword rubric grading,
lexicon red flags, the Imran number-mismatch fixture) lives in `app.llm.tasks`,
because it needs structured inputs that a raw text prompt does not carry. This class
exists so that `LLM_PROVIDER=mock` is an explicit, inspectable choice.
"""

from __future__ import annotations

from typing import Any

from app.llm.base import Tier


class MockProvider:
    name = "mock"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, system: str, user: str, schema: dict[str, Any], tier: Tier = "quality") -> dict[str, Any]:
        self.calls.append({"system": system, "user": user, "schema": schema})
        return {}

    def complete_text(self, system: str, user: str, tier: Tier = "quality") -> str:
        self.calls.append({"system": system, "user": user})
        return user
