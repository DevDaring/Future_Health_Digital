"""OpenAI-compatible relay provider (NanoGPT, LinkAPI, Azure OpenAI).

Endpoints are tried in order per tier; the first that answers wins. A refusal
(`content_filter`) or truncation (`length`) raises `LLMRefusal` and is *not* retried on
another endpoint, because a refusal is a signal for a human, not a transport error.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.llm.base import LLMError, LLMRefusal, Tier

log = logging.getLogger("wasl.llm")


@dataclass
class Endpoint:
    label: str
    base_url: str
    api_key: str
    model: str
    azure: bool = False


def _extract_json(text: str) -> dict[str, Any]:
    """Parse the first complete JSON object in a reply (models sometimes add a second
    object or prose after it)."""
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.S)
    if fence:
        t = fence.group(1)
    start = t.find("{")
    if start < 0:
        raise ValueError("no JSON object in reply")
    obj, _ = json.JSONDecoder(strict=False).raw_decode(t[start:])  # strict=False: raw newlines in strings
    if not isinstance(obj, dict):
        raise ValueError("JSON reply is not an object")
    return obj


def _clean(text: str) -> str:
    """Drop BOMs and U+FFFD replacement characters that relays occasionally emit."""
    return text.replace("\ufeff", "").replace("\ufffd", "").strip()


def schema_instructions(schema: dict[str, Any]) -> str:
    """Describe the expected keys in words. Pasting a raw JSON Schema makes some models
    (Gemini Flash) echo the schema back instead of answering."""
    lines = []
    for key, spec in schema.get("properties", {}).items():
        kind = spec.get("type", "string")
        if kind == "array":
            kind = f"list of {spec.get('items', {}).get('type', 'string')}s"
        if "enum" in spec:
            kind += " (one of: " + ", ".join(spec["enum"]) + ")"
        if spec.get("description"):
            kind += f" — {spec['description']}"
        lines.append(f'- "{key}": {kind}')
    return (
        "\n\nAnswer with ONE JSON object containing your actual answer (not a schema), with exactly these keys:\n"
        + "\n".join(lines)
        + "\nNo prose, no markdown."
    )


class RelayProvider:
    def __init__(self, fast: list[Endpoint], quality: list[Endpoint], timeout_s: float = 40.0, max_tokens: int = 2000) -> None:
        self.fast = fast
        self.quality = quality
        self.timeout_s = timeout_s
        self.max_tokens = max_tokens
        self.name = "relay:" + ",".join(e.label for e in quality or fast)
        self._client = httpx.Client(timeout=timeout_s)

    def _chain(self, tier: Tier) -> list[Endpoint]:
        return (self.fast if tier == "fast" else self.quality) or self.fast or self.quality

    def _call(self, ep: Endpoint, system: str, user: str, json_mode: bool, max_tokens: int) -> str:
        body: dict[str, Any] = {
            "model": ep.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if ep.azure:
            url = f"{ep.base_url.rstrip('/')}/openai/deployments/{ep.model}/chat/completions?api-version=2024-06-01"
            headers = {"api-key": ep.api_key}
        else:
            url = f"{ep.base_url.rstrip('/')}/chat/completions"
            headers = {"Authorization": f"Bearer {ep.api_key}"}
        resp = self._client.post(url, json=body, headers=headers)
        if resp.status_code >= 400:
            raise LLMError(f"{ep.label} HTTP {resp.status_code}")
        # Some relays omit the charset; never let the client guess (Arabic became mojibake).
        data = json.loads(resp.content.decode("utf-8"))
        choice = (data.get("choices") or [{}])[0]
        finish = choice.get("finish_reason")
        content = _clean((choice.get("message") or {}).get("content") or "")
        if finish == "content_filter":
            raise LLMRefusal("refusal")
        if finish == "length":
            raise LLMRefusal("max_tokens")
        if not content:
            raise LLMError(f"{ep.label} empty response")
        return content

    def _run(self, system: str, user: str, tier: Tier, json_mode: bool, validate: Any = None) -> str:
        """Try each endpoint in order. Transport errors, invalid output and a refusal from
        one model family move on to the next endpoint; if every endpoint refused, the
        refusal propagates (the caller sends approved text and escalates to a human)."""
        errors: list[str] = []
        refusal: LLMRefusal | None = None
        for ep in self._chain(tier):
            t0 = time.monotonic()
            try:
                out = self._call(ep, system, user, json_mode, self.max_tokens)
                if validate is not None:
                    validate(out)
                log.info("llm %s %s ok in %.1fs", ep.label, tier, time.monotonic() - t0)
                return out
            except LLMRefusal as exc:
                log.warning("llm %s stop_reason=%s", ep.label, exc.reason)
                refusal = exc
            except (httpx.HTTPError, LLMError, ValueError) as exc:
                log.warning("llm %s failed: %s", ep.label, exc)
                errors.append(f"{ep.label}: {exc}")
        if refusal is not None and not errors:
            raise refusal
        raise LLMError("; ".join(errors) or "no endpoints configured")

    def complete_json(self, system: str, user: str, schema: dict[str, Any], tier: Tier = "quality") -> dict[str, Any]:
        required = list(schema.get("required") or schema.get("properties", {}).keys())

        def validate(text: str) -> None:
            obj = _extract_json(text)
            if "properties" in obj and "type" in obj:
                raise ValueError("model echoed the schema")
            missing = [k for k in required if k not in obj]
            if missing:
                raise ValueError(f"missing keys {missing}")

        text = self._run(system + schema_instructions(schema), user, tier, json_mode=True, validate=validate)
        return _extract_json(text)

    def complete_text(self, system: str, user: str, tier: Tier = "quality") -> str:
        return self._run(system, user, tier, json_mode=False)
