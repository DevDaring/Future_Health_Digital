"""Anthropic provider using the official SDK (spec section 8.1).

Enabled with LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY. Model from LLM_MODEL
(default claude-opus-5-5; claude-sonnet-5-5 / claude-haiku-5-5 are cheaper for chat).

Rules followed (per the spec for this model family):
* JSON via `output_config={"format": {"type": "json_schema", "schema": ...}}` with a
  strict schema (additionalProperties false, all properties required).
* `output_config={"effort": "low"}` for translation/chat turns.
* No temperature / top_p / disabled-thinking / assistant prefill (HTTP 400 here).
* `stop_reason` of "refusal" or "max_tokens" → LLMRefusal (caller falls back + escalates).
* RateLimitError, APIConnectionError, APIStatusError caught separately → LLMError.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.llm.base import LLMError, LLMRefusal, Tier

log = logging.getLogger("wasl.llm.anthropic")


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Make every object schema strict: additionalProperties false, all keys required."""
    s = json.loads(json.dumps(schema))

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(s)
    return s


class AnthropicProvider:
    def __init__(self, api_key: str, model: str = "claude-opus-5-5") -> None:
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.name = f"anthropic:{model}"

    def _create(self, system: str, user: str, output_config: dict[str, Any]) -> str:
        a = self._anthropic
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config=output_config,
            )
        except a.RateLimitError as exc:
            log.warning("anthropic rate limited: %s", exc)
            raise LLMError("rate_limited") from exc
        except a.APIConnectionError as exc:
            log.warning("anthropic connection error: %s", exc)
            raise LLMError("connection") from exc
        except a.APIStatusError as exc:
            log.warning("anthropic status %s", exc.status_code)
            raise LLMError(f"status_{exc.status_code}") from exc
        if resp.stop_reason in ("refusal", "max_tokens"):
            raise LLMRefusal(str(resp.stop_reason))
        for block in resp.content:
            if getattr(block, "type", "") == "text":
                return block.text
        raise LLMError("no text block")

    def complete_json(self, system: str, user: str, schema: dict[str, Any], tier: Tier = "quality") -> dict[str, Any]:
        cfg: dict[str, Any] = {"format": {"type": "json_schema", "schema": strict_schema(schema)}, "effort": "low"}
        text = self._create(system, user, cfg)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError("invalid json") from exc

    def complete_text(self, system: str, user: str, tier: Tier = "quality") -> str:
        return self._create(system, user, {"effort": "low"}).strip()
