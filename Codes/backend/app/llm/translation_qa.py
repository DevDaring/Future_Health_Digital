"""Back-translation verification (killer feature 2, spec section 8.3).

    approved EN template → simplify (EN) → translate → back-translate → QA
    QA = (a) deterministic entity check: numbers / units / dates / test names identical
         (b) LLM judge: medical meaning preserved, score 0–1 + discrepancies
    pass = score ≥ threshold AND entity_match → send; otherwise fall back to the
    clinician-approved translation (or English + interpreter offer) and queue for review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

TEST_NAMES = ("HbA1c", "FIT", "BI-RADS")

_DIGIT_MAP = {}
for zero in ("٠", "۰", "०", "০", "൦"):
    base = ord(zero)
    for i in range(10):
        _DIGIT_MAP[chr(base + i)] = str(i)
_DIGIT_MAP["٫"] = "."  # Arabic decimal separator
_DIGIT_TABLE = str.maketrans(_DIGIT_MAP)
_NUM = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)?(?![A-Za-z])")  # skip digits inside words like HbA1c


def normalise_digits(text: str) -> str:
    return text.translate(_DIGIT_TABLE)


def extract_numbers(text: str) -> list[str]:
    """Sorted list (multiset) of numbers, with Eastern digits and decimal commas normalised."""
    return sorted(n.replace(",", ".") for n in _NUM.findall(normalise_digits(text)))


def entity_check(source_en: str, translated: str, back_en: str) -> tuple[bool, list[str]]:
    issues: list[str] = []
    src_nums = extract_numbers(source_en)
    tr_nums = extract_numbers(translated)
    bk_nums = extract_numbers(back_en)
    if src_nums != tr_nums:
        issues.append(f"numbers in translation {tr_nums} ≠ source {src_nums}")
    if src_nums != bk_nums:
        issues.append(f"numbers in back-translation {bk_nums} ≠ source {src_nums}")
    # Case-sensitive on purpose: "FIT" the stool test, not "fit" as in "fits your shift".
    for name in TEST_NAMES:
        pat = rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])"
        if re.search(pat, source_en):
            if not re.search(pat, translated):
                issues.append(f"test name '{name}' missing in translation")
            if not re.search(pat, back_en):
                issues.append(f"test name '{name}' missing in back-translation")
    return (not issues), issues


@dataclass
class PipelineResult:
    source_en: str
    simplified_en: str
    translated: str
    back_translated: str
    judge_score: float
    entity_match: bool
    discrepancies: list[str] = field(default_factory=list)
    passed: bool = True
    fell_back: bool = False
    final_text: str = ""
    final_source: str = "checked"  # checked | approved_translation | english_interpreter
    provider: str = "mock"

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def apply_demo_fault(translated: str, fault: str | None, value: str | None) -> str:
    """Demo fault injection (labelled in the UI): simulate a machine-translation digit swap,
    e.g. 7.4 → 4.7, so the QA catch is reproducible in every demo run."""
    if fault != "mt_number_swap" or not value:
        return translated
    swapped = value[::-1] if "." in value else value
    for variant in (value, value.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")), value.translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))):
        if variant in translated:
            return translated.replace(variant, swapped, 1)
    return translated
