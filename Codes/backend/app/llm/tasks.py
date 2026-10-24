"""Clinical-facing LLM tasks with deterministic mock behaviour and safe fallbacks.

Every task has two implementations:
* mock  — deterministic, offline (fixture translations, keyword rubric, lexicon);
* model — prompts sent through the PII-firewalled provider.

On a transport error the task logs it and falls back to the mock implementation
(`self.fallbacks` records this). On a refusal / max_tokens the `LLMRefusal` propagates so
the caller can use approved text and open an `llm_refusal` escalation.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.llm.base import LLMError
from app.llm.translation_qa import extract_numbers, normalise_digits
from app.navigator import prompts
from app.navigator.content import LANG_NAMES, normalise, quick_reply_index, red_flag_lexicon

log = logging.getLogger("wasl.tasks")

BARRIER_KEYWORDS: list[tuple[str, list[str]]] = [
    ("cost", ["cost", "money", "pay", "price", "afford", "expensive", "insurance", "fee"]),
    ("time", ["night", "shift", "work", "time off", "weekday", "busy", "job", "duty", "leave"]),
    ("transport", ["far", "travel", "transport", "distance", "bus", "taxi", "car"]),
    ("fear", ["scared", "afraid", "worried", "fear", "nervous", "anxious"]),
    ("language", ["language", "don't understand", "do not understand", "interpreter", "english"]),
    ("family", ["family", "children", "husband", "wife", "kids", "child", "mother"]),
    ("none", ["no problem", "can come", "fine", "okay", "ok", "sure", "yes"]),
]
REFUSAL = ["don't want", "do not want", "refuse", "no thanks", "not interested", "won't come", "will not come"]
HUMAN = ["human", "talk to a person", "real person", "talk to someone", "call me", "nurse"]


class Tasks:
    def __init__(self, provider: Any) -> None:
        self.provider = provider
        self.is_mock = getattr(provider, "name", "mock") == "mock"
        self.fallbacks: list[str] = []

    @property
    def name(self) -> str:
        return getattr(self.provider, "name", "mock")

    # ------------------------------------------------------------------ simplify
    def simplify(self, text_en: str, literacy: int) -> str:
        if self.is_mock:
            return text_en
        try:
            out = self.provider.complete_text(prompts.navigator_system(literacy), prompts.simplify_user(text_en, literacy), tier="fast")
            # Guard: never accept a simplification that lost a number.
            return out if extract_numbers(out) == extract_numbers(text_en) else text_en
        except LLMError as exc:
            self._fallback("simplify", exc)
            return text_en

    # ----------------------------------------------------------------- translate
    def translate(self, text_en: str, lang: str, fixture_text: str | None) -> str:
        if lang == "en":
            return text_en
        if self.is_mock:
            return fixture_text or f"[{lang}] {text_en}"
        try:
            return self.provider.complete_text(prompts.translator_system(lang), text_en)
        except LLMError as exc:
            self._fallback("translate", exc)
            return fixture_text or f"[{lang}] {text_en}"

    def back_translate(self, translated: str, lang: str, source_en: str) -> str:
        if lang == "en":
            return translated
        if self.is_mock:
            return source_en  # spec: mock back-translation returns the source text
        try:
            return self.provider.complete_text(prompts.back_translator_system(lang), translated, tier="fast")
        except LLMError as exc:
            self._fallback("back_translate", exc)
            return source_en

    def to_english(self, text: str, lang: str) -> str:
        if lang == "en":
            return text
        known = quick_reply_index().get(normalise(text))
        if known:
            return known
        if self.is_mock:
            return text
        try:
            return self.provider.complete_text(prompts.back_translator_system(lang), text, tier="fast")
        except LLMError as exc:
            self._fallback("to_english", exc)
            return text

    # --------------------------------------------------------------------- judge
    def judge(self, source_en: str, translated: str, back_en: str, lang: str) -> dict[str, Any]:
        if self.is_mock:
            return mock_judge(source_en, translated)
        try:
            res = self.provider.complete_json(
                prompts.JUDGE_SYSTEM,
                prompts.judge_user(source_en, translated, back_en, LANG_NAMES.get(lang, lang)),
                prompts.JUDGE_SCHEMA,
                tier="fast",  # a different model family from the translator: an independent check
            )
            score = float(res.get("score", 0.0))
            return {"score": max(0.0, min(1.0, score)), "discrepancies": [str(x) for x in res.get("discrepancies", [])][:8]}
        except (LLMError, ValueError, TypeError) as exc:
            self._fallback("judge", exc)
            return mock_judge(source_en, translated)

    # ---------------------------------------------------------------- understand
    def understand(self, text: str, lang: str, step: str, program: str) -> dict[str, Any]:
        """English meaning + intent + barrier + red flag for one patient message."""
        lexicon_hit = red_flag_lexicon_match(text)
        if self.is_mock:
            english = self.to_english(text, lang)
            res = mock_understand(english)
        else:
            try:
                res = self.provider.complete_json(
                    prompts.UNDERSTAND_SYSTEM,
                    prompts.understand_user(text, LANG_NAMES.get(lang, lang), step, program),
                    prompts.UNDERSTAND_SCHEMA,
                    tier="fast",
                )
                res = {
                    "answer_en": str(res.get("answer_en") or text),
                    "intent": str(res.get("intent") or "other"),
                    "barrier": str(res.get("barrier") or "none"),
                    "red_flag": bool(res.get("red_flag")),
                    "red_flag_reason": str(res.get("red_flag_reason") or ""),
                }
            except (LLMError, ValueError, TypeError) as exc:
                self._fallback("understand", exc)
                english = self.to_english(text, lang)
                res = mock_understand(english)
        if not lexicon_hit:
            lexicon_hit = red_flag_lexicon_match(res["answer_en"])
        if lexicon_hit:
            res["red_flag"] = True
            res["red_flag_reason"] = res.get("red_flag_reason") or f"lexicon:{lexicon_hit}"
        res["red_flag_source"] = "lexicon" if lexicon_hit else ("llm" if res.get("red_flag") else "")
        return res

    # ---------------------------------------------------------------- teach-back
    def grade_teach_back(self, answer_en: str, program: str, rubric: dict[str, list[str]]) -> dict[str, Any]:
        if self.is_mock:
            return keyword_grade(answer_en, rubric)
        try:
            res = self.provider.complete_json(
                prompts.TEACH_BACK_SYSTEM, prompts.teach_back_user(answer_en, program, rubric), prompts.TEACH_BACK_SCHEMA, tier="fast"
            )
            out = {k: bool(res.get(k)) for k in ("understands_result", "knows_next_step", "knows_when")}
            out["passed"] = all(out.values())
            out["feedback"] = str(res.get("feedback") or "")
            out["method"] = "llm"
            return out
        except (LLMError, ValueError, TypeError) as exc:
            self._fallback("teach_back", exc)
            return keyword_grade(answer_en, rubric)

    def _fallback(self, task: str, exc: Exception) -> None:
        log.warning("LLM task %s failed (%s); using mock behaviour", task, exc)
        self.fallbacks.append(task)


# ---------------------------------------------------------------------- mocks

def mock_judge(source_en: str, translated: str) -> dict[str, Any]:
    src = extract_numbers(source_en)
    tr = extract_numbers(normalise_digits(translated))
    if src != tr:
        missing = sorted(set(src) - set(tr))
        extra = sorted(set(tr) - set(src))
        return {
            "score": 0.42,
            "discrepancies": [f"number mismatch: expected {', '.join(missing) or '—'}, found {', '.join(extra) or '—'}"],
        }
    return {"score": 0.96, "discrepancies": []}


def mock_understand(english: str) -> dict[str, Any]:
    t = english.lower()
    intent = "other"
    barrier = "none"
    if any(w in t for w in HUMAN):
        intent = "human"
    elif any(w in t for w in REFUSAL):
        intent = "refusal"
    else:
        for name, words in BARRIER_KEYWORDS:
            if any(re.search(rf"\b{re.escape(w)}\b", t) for w in words):
                barrier = name
                intent = "barrier"
                break
    return {"answer_en": english, "intent": intent, "barrier": barrier, "red_flag": False, "red_flag_reason": ""}


def keyword_grade(answer_en: str, rubric: dict[str, list[str]]) -> dict[str, Any]:
    t = answer_en.lower()
    out: dict[str, Any] = {k: any(w in t for w in words) for k, words in rubric.items()}
    out["passed"] = all(out[k] for k in rubric)
    missing = [k for k in rubric if not out[k]]
    out["feedback"] = "All key points explained." if out["passed"] else "Missing: " + ", ".join(missing)
    out["method"] = "keyword_rubric"
    return out


def red_flag_lexicon_match(text: str) -> str | None:
    t = text.lower()
    for cat, words in red_flag_lexicon().items():
        for w in words:
            if w and w in t:
                return cat
    return None
