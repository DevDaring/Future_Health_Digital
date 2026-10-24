"""Access to fixtures: approved templates, fixture translations, phrases and red-flag
lexicons. The database is the source of truth at runtime for templates; the YAML/JSON
fixtures seed it and back the offline mock provider."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import yaml

from app.config import FIXTURES_DIR

LANGS = ("en", "ar", "hi", "ur", "ml", "bn", "tl")
RTL = {"ar", "ur"}
LANG_NAMES = {"en": "English", "ar": "Arabic", "hi": "Hindi", "ur": "Urdu", "ml": "Malayalam", "bn": "Bengali", "tl": "Tagalog"}


@lru_cache
def templates_fixture() -> dict[str, Any]:
    return yaml.safe_load((FIXTURES_DIR / "templates.yaml").read_text())


def template_key(program: str, severity: str, key: str) -> str:
    return f"{program}.{severity}.{key}"


def flat_templates() -> dict[str, str]:
    t = templates_fixture()
    out = {f"ANY.any.{k}": v for k, v in t["generic"].items()}
    for prog, sevs in t["programs"].items():
        for sev, keys in sevs.items():
            for k, v in keys.items():
                out[f"{prog}.{sev}.{k}"] = v
    return out


@lru_cache
def fixture_translations(lang: str) -> dict[str, str]:
    path = FIXTURES_DIR / "approved_translations" / f"{lang}.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    data.pop("_note", None)
    return data


@lru_cache
def phrases(lang: str) -> dict[str, dict[str, str]]:
    base = json.loads((FIXTURES_DIR / "phrases_en.json").read_text())
    if lang == "en":
        return base
    path = FIXTURES_DIR / "phrases" / f"{lang}.json"
    if not path.exists():
        return base
    tr = json.loads(path.read_text())
    return {sec: {**base[sec], **tr.get(sec, {})} for sec in base}


@lru_cache
def quick_reply_index() -> dict[str, str]:
    """Normalised quick-reply text in any language → English meaning (for the mock)."""
    en = phrases("en")["quick"]
    idx: dict[str, str] = {}
    for lang in LANGS:
        for key, text in phrases(lang)["quick"].items():
            idx[normalise(text)] = en[key]
    return idx


@lru_cache
def red_flag_lexicon() -> dict[str, list[str]]:
    """category → phrases across all languages (lower-cased)."""
    out: dict[str, list[str]] = {}
    for path in sorted((FIXTURES_DIR / "red_flags").glob("*.yaml")):
        data = yaml.safe_load(path.read_text()) or {}
        for cat, items in data.items():
            out.setdefault(cat, []).extend(str(x).lower() for x in (items or []) if str(x).strip())
    return out


def normalise(text: str) -> str:
    return " ".join(text.lower().strip().rstrip(".!?।۔").split())


def safe_format(body: str, variables: dict[str, Any]) -> str:
    class _D(dict):  # leave unknown placeholders visible rather than crash
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    return body.format_map(_D(variables))
