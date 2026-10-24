"""PII firewall (spec section 8.2).

Before any LLM call, identity strings are replaced by opaque tokens such as ⟦NAME_1⟧;
after the call the tokens are restored. Known identity values (name parts, phone,
Emirates ID, patient code, staff names) are replaced first, then regexes catch phone
numbers, e-mails, Emirates-ID patterns and dates of birth that slipped through.

Only a SHA-256 hash of each redacted payload is logged, never the payload itself.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.llm.base import Tier

log = logging.getLogger("wasl.pii")

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EID", re.compile(r"\b784[-\s]?\d{4}[-\s]?\d{7}[-\s]?\d\b|\b784-[\d*]{4}-[\d*]{7}-[\d*]\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("PHONE", re.compile(r"(?:\+971|00971|\b0)[\s-]?5\d[\s-]?\d{3}[\s-]?\d{4}\b")),
    ("DOB", re.compile(r"\b(?:0?[1-9]|[12]\d|3[01])[/.-](?:0?[1-9]|1[0-2])[/.-](?:19|20)\d{2}\b")),
    ("PID", re.compile(r"\bWASL-P\d{5}\b")),
]


@dataclass
class Redaction:
    mapping: dict[str, str] = field(default_factory=dict)  # token -> original
    reverse: dict[str, str] = field(default_factory=dict)  # original -> token
    counters: dict[str, int] = field(default_factory=dict)

    def token_for(self, kind: str, value: str) -> str:
        if value in self.reverse:
            return self.reverse[value]
        self.counters[kind] = self.counters.get(kind, 0) + 1
        tok = f"⟦{kind}_{self.counters[kind]}⟧"
        self.mapping[tok] = value
        self.reverse[value] = tok
        return tok


class PIIFirewall:
    def __init__(self, known: dict[str, list[str]] | None = None) -> None:
        # known: kind -> values, e.g. {"NAME": ["Ramesh Kumar", "Ramesh", "Kumar"], "PHONE": [...]}
        self.known = known or {}

    def redact(self, text: str, red: Redaction | None = None) -> tuple[str, Redaction]:
        red = red or Redaction()
        out = text
        # Longest values first so "Ramesh Kumar" is replaced before "Ramesh".
        items = sorted(
            ((kind, v) for kind, vals in self.known.items() for v in vals if v and len(v) >= 2),
            key=lambda kv: -len(kv[1]),
        )
        for kind, value in items:
            if value in out:
                out = re.sub(rf"(?<!\w){re.escape(value)}(?!\w)", red.token_for(kind, value), out)
        for kind, pat in PATTERNS:
            out = pat.sub(lambda m, k=kind: red.token_for(k, m.group(0)), out)
        return out, red

    @staticmethod
    def restore(text: str, red: Redaction) -> str:
        for tok, value in red.mapping.items():
            text = text.replace(tok, value)
        return text


def payload_hash(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


class FirewalledProvider:
    """Wraps any provider so *every* outgoing prompt is redacted and every reply restored.
    `sent` keeps the redacted payloads of this request (used by the PII unit test)."""

    def __init__(self, inner: Any, firewall: PIIFirewall) -> None:
        self.inner = inner
        self.firewall = firewall
        self.name = getattr(inner, "name", "unknown")
        self.sent: list[str] = []

    def _prep(self, system: str, user: str) -> tuple[str, str, Redaction]:
        red = Redaction()
        s, red = self.firewall.redact(system, red)
        u, red = self.firewall.redact(user, red)
        self.sent.append(s + "\n" + u)
        log.info("llm payload sha256=%s", payload_hash(s, u))
        return s, u, red

    def complete_json(self, system: str, user: str, schema: dict[str, Any], tier: Tier = "quality") -> dict[str, Any]:
        s, u, red = self._prep(system, user)
        out = self.inner.complete_json(s, u, schema, tier)
        return _restore_obj(out, red)

    def complete_text(self, system: str, user: str, tier: Tier = "quality") -> str:
        s, u, red = self._prep(system, user)
        return PIIFirewall.restore(self.inner.complete_text(s, u, tier), red)


def _restore_obj(obj: Any, red: Redaction) -> Any:
    if isinstance(obj, str):
        return PIIFirewall.restore(obj, red)
    if isinstance(obj, list):
        return [_restore_obj(x, red) for x in obj]
    if isinstance(obj, dict):
        return {k: _restore_obj(v, red) for k, v in obj.items()}
    return obj
