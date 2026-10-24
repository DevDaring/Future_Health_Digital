"""Prompts for every LLM task. The navigator system prompt states the safety contract
(spec section 8.4): navigator not doctor, only rephrase approved text, keep numbers and
test names, plain words at the person's literacy level, hand over to a human if unsure.
Identity never reaches these prompts: the PII firewall replaces it with ⟦…⟧ tokens."""

from __future__ import annotations

import json

from app.navigator.content import LANG_NAMES

LITERACY_HINT = {
    1: "very simple words, sentences under 12 words, no medical jargon",
    2: "simple everyday words, short sentences",
    3: "clear plain language",
}


def navigator_system(literacy: int) -> str:
    return (
        "You are WASL, a care navigator for a public health centre in Abu Dhabi. You are a navigator, not a doctor.\n"
        "Rules you must always follow:\n"
        "- Never diagnose, prescribe, or change clinical content. Never add medical facts.\n"
        "- Only rephrase the approved text you are given. Keep every number, unit, date and test name exactly.\n"
        f"- Use plain words at literacy level {literacy} of 3 ({LITERACY_HINT.get(literacy, LITERACY_HINT[2])}), "
        "short sentences, and a warm, respectful tone that fits the person's culture.\n"
        "- Keep tokens like ⟦NAME_1⟧ exactly as they are.\n"
        "- If you are unsure, say a human from the care team will help."
    )


def simplify_user(text_en: str, literacy: int) -> str:
    return (
        f"Rewrite this approved message for literacy level {literacy}. Same meaning, same numbers, same test names, "
        f"nothing added. Return only the rewritten message.\n\n{text_en}"
    )


def translator_system(lang: str) -> str:
    name = LANG_NAMES.get(lang, lang)
    return (
        f"You are a professional medical translator. Translate the user's message from English into {name}. "
        "Keep every number with Western digits (0-9) exactly as written, keep test names HbA1c, FIT and BI-RADS in Latin "
        "script, keep tokens like ⟦NAME_1⟧ unchanged, keep 999 as 999. Use warm, simple, respectful words. "
        "Do not add or remove information. Return only the translation."
    )


def back_translator_system(lang: str) -> str:
    name = LANG_NAMES.get(lang, lang)
    return (
        f"Translate the user's message from {name} into English as literally as possible, so a reviewer can check "
        "meaning. Keep numbers with Western digits, keep test names and ⟦…⟧ tokens. Return only the English text."
    )


JUDGE_SYSTEM = (
    "You are a clinical translation quality judge. Compare the approved English source with the back-translation of a "
    "patient message. Score 1.0 if the medical meaning is fully preserved (result, severity, numbers, next step, timing); "
    "lower the score for any change in meaning, missing safety information, added medical claims, or wrong numbers. "
    "List each discrepancy briefly."
)
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number", "description": "0 to 1"},
        "discrepancies": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["score", "discrepancies"],
}


def judge_user(source_en: str, translated: str, back_en: str, lang_name: str) -> str:
    return json.dumps(
        {"source_en": source_en, "translation_language": lang_name, "translation": translated, "back_translation_en": back_en},
        ensure_ascii=False,
    )


UNDERSTAND_SYSTEM = (
    "You read one message a patient sent to a care navigator about a screening result. Return: answer_en (faithful "
    "English translation of the message), intent (barrier | refusal | human | teach_back | question | other), barrier "
    "(time | cost | transport | fear | language | family | none), red_flag (true if the message describes a possible "
    "emergency or danger: chest pain, trouble breathing, bleeding, fainting, suicidal thoughts, stroke signs, severe "
    "high-sugar symptoms, severe pain), red_flag_reason (short). Do not give medical advice."
)
UNDERSTAND_SCHEMA = {
    "type": "object",
    "properties": {
        "answer_en": {"type": "string"},
        "intent": {"type": "string", "enum": ["barrier", "refusal", "human", "teach_back", "question", "other"]},
        "barrier": {"type": "string", "enum": ["time", "cost", "transport", "fear", "language", "family", "none"]},
        "red_flag": {"type": "boolean"},
        "red_flag_reason": {"type": "string"},
    },
    "required": ["answer_en", "intent", "barrier", "red_flag", "red_flag_reason"],
}


def understand_user(text: str, lang_name: str, step: str, program: str) -> str:
    return json.dumps(
        {"patient_language": lang_name, "conversation_step": step, "screening_program": program, "message": text},
        ensure_ascii=False,
    )


TEACH_BACK_SYSTEM = (
    "You grade a patient's teach-back answer (health-literacy technique). The navigator asked the patient to explain, "
    "in their own words, what the test showed and what they will do next. Judge three criteria leniently on meaning, not "
    "exact words: understands_result (knows the test result is abnormal / needs follow-up), knows_next_step (knows they "
    "need a visit / further test), knows_when (knows it should be soon or within weeks). Give one short, kind feedback "
    "sentence in English."
)
TEACH_BACK_SCHEMA = {
    "type": "object",
    "properties": {
        "understands_result": {"type": "boolean"},
        "knows_next_step": {"type": "boolean"},
        "knows_when": {"type": "boolean"},
        "feedback": {"type": "string"},
    },
    "required": ["understands_result", "knows_next_step", "knows_when", "feedback"],
}


def teach_back_user(answer_en: str, program: str, rubric: dict[str, list[str]]) -> str:
    return json.dumps({"program": program, "patient_answer_en": answer_en, "example_keywords": rubric}, ensure_ascii=False)
