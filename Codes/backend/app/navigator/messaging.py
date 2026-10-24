"""Outgoing patient messages: approved template → PII firewall → LLM pipeline → QA →
persisted message with its translation check (spec section 8.3).

The compute step (`run_pipeline`) is pure and thread-safe, so several messages of one
turn are prepared in parallel; database writes happen afterwards on the request's
session. Passing results are cached (`llm_cache`), so a repeated message for the same
person, language and literacy is instant.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.config import get_settings
from app.llm.base import LLMRefusal
from app.llm.factory import get_provider
from app.llm.pii_firewall import FirewalledProvider, PIIFirewall
from app.llm.tasks import Tasks
from app.llm.translation_qa import PipelineResult, apply_demo_fault, entity_check
from app.loop_engine import service
from app.models import (
    ApprovedTranslation,
    CareLoop,
    ContentTemplate,
    Conversation,
    LLMCache,
    Message,
    PatientIdentity,
    ReviewItem,
    TranslationCheck,
    User,
)
from app.navigator.content import safe_format, templates_fixture

log = logging.getLogger("wasl.messaging")


@dataclass
class Rendered:
    key: str
    template: ContentTemplate | None
    text_en: str
    fixture_text: str | None
    extra_meta: dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------------- vars

def loop_vars(db: Session, loop: CareLoop) -> dict[str, Any]:
    se = loop.screening
    ident = db.scalar(select(PatientIdentity).where(PatientIdentity.patient_id == loop.patient_id))
    first = ident.full_name.split()[0] if ident else "there"
    s = get_settings()
    value = "" if se.value_numeric is None else (f"{se.value_numeric:.1f}" if se.program == "DIABETES" else f"{se.value_numeric:g}")
    tf = templates_fixture()
    risk = tf["programs"].get(se.program, {}).get(se.severity, {}).get("risk_statement", "")
    return {
        "first_name": first,
        "test_name": tf["test_names"].get(se.program, se.test_code),
        "value": value,
        "value_text": se.value_text or value,
        "category": se.category,
        "sla_days": s.sla_days(se.severity),
        "risk_statement": risk,
    }


def find_template(db: Session, loop: CareLoop, key: str) -> ContentTemplate | None:
    se = loop.screening
    for program, severity in ((se.program, se.severity), ("ANY", "any")):
        t = db.scalar(
            select(ContentTemplate)
            .where(
                ContentTemplate.key == key,
                ContentTemplate.program == program,
                ContentTemplate.severity == severity,
                ContentTemplate.status == "approved",
            )
            .order_by(ContentTemplate.version.desc())
            .limit(1)
        )
        if t is not None:
            return t
    return None


def render(db: Session, loop: CareLoop, key: str, lang: str, extra: dict[str, Any] | None = None) -> Rendered:
    tmpl = find_template(db, loop, key)
    variables = {**loop_vars(db, loop), **(extra or {})}
    if tmpl is None:
        raise KeyError(f"no approved template for {key}")
    text_en = safe_format(tmpl.body, variables)
    fixture = None
    if lang != "en":
        tr = db.scalar(
            select(ApprovedTranslation).where(ApprovedTranslation.template_id == tmpl.id, ApprovedTranslation.language == lang)
        )
        if tr is not None:
            fixture = safe_format(tr.body, variables)
    return Rendered(key=key, template=tmpl, text_en=text_en, fixture_text=fixture)


# ------------------------------------------------------------------------- firewall

def firewall_for(db: Session, loop: CareLoop) -> PIIFirewall:
    ident = db.scalar(select(PatientIdentity).where(PatientIdentity.patient_id == loop.patient_id))
    known: dict[str, list[str]] = {"PID": [loop.patient.code]}
    if ident:
        known["NAME"] = [ident.full_name, *ident.full_name.split()]
        known["PHONE"] = [ident.phone]
        known["EID"] = [ident.emirates_id_masked]
    known["STAFF"] = [u.display_name for u in db.scalars(select(User))]
    return PIIFirewall(known)


# ------------------------------------------------------------------------- pipeline

def run_pipeline(tasks: Tasks, r: Rendered, lang: str, literacy: int, fault: str | None, value: str | None) -> PipelineResult:
    """Simplify → translate → back-translate → entity check + judge. Pure (no DB)."""
    threshold = get_settings().translation_pass_threshold
    simplified = tasks.simplify(r.text_en, literacy)
    if lang == "en":
        ok, issues = entity_check(r.text_en, simplified, simplified)
        final = simplified if ok else r.text_en
        return PipelineResult(r.text_en, simplified, final, final, 1.0, True, issues, True, False, final, "checked", tasks.name)
    translated = tasks.translate(simplified, lang, r.fixture_text)
    translated = apply_demo_fault(translated, fault, value)
    back = tasks.back_translate(translated, lang, simplified)
    entity_ok, issues = entity_check(simplified, translated, back)
    verdict = tasks.judge(simplified, translated, back, lang)
    discrepancies = issues + [d for d in verdict["discrepancies"] if d not in issues]
    passed = entity_ok and verdict["score"] >= threshold
    res = PipelineResult(
        source_en=r.text_en,
        simplified_en=simplified,
        translated=translated,
        back_translated=back,
        judge_score=float(verdict["score"]),
        entity_match=entity_ok,
        discrepancies=discrepancies,
        passed=passed,
        provider=tasks.name,
    )
    if passed:
        res.final_text, res.final_source = translated, "checked"
    elif r.fixture_text:
        res.fell_back, res.final_text, res.final_source = True, r.fixture_text, "approved_translation"
    else:
        res.fell_back, res.final_source = True, "english_interpreter"
        res.final_text = r.text_en
    return res


def _cache_key(provider: str, r: Rendered, lang: str, literacy: int, fault: str | None) -> str:
    raw = json.dumps(
        [provider, r.key, r.template.version if r.template else 0, lang, literacy, r.text_en, r.fixture_text, fault],
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def prepare(db: Session, loop: CareLoop, items: list[Rendered], lang: str) -> list[tuple[PipelineResult, str | None]]:
    """Run the pipeline for several messages (parallel, cached). Returns (result, refusal)."""
    literacy = loop.patient.literacy_level
    fault = loop.demo_fault
    value = loop_vars(db, loop)["value"]
    provider = get_provider()
    firewall = firewall_for(db, loop)
    out: list[tuple[PipelineResult, str | None] | None] = [None] * len(items)
    todo: list[int] = []
    keys = [_cache_key(getattr(provider, "name", "mock"), r, lang, literacy, fault) for r in items]
    for i, k in enumerate(keys):
        hit = db.get(LLMCache, k)
        if hit is not None:
            out[i] = (PipelineResult(**hit.value), None)
        else:
            todo.append(i)

    def work(i: int) -> tuple[PipelineResult, str | None, bool]:
        tasks = Tasks(FirewalledProvider(provider, firewall))
        try:
            res = run_pipeline(tasks, items[i], lang, literacy, fault, value)
            return res, None, not tasks.fallbacks
        except LLMRefusal as exc:
            r = items[i]
            final = r.fixture_text or r.text_en
            res = PipelineResult(r.text_en, r.text_en, final, final, 0.0, False, [f"LLM {exc.reason}"], False, True, final,
                                 "approved_translation" if r.fixture_text else "english_interpreter", tasks.name)
            return res, exc.reason, False

    if todo:
        with ThreadPoolExecutor(max_workers=min(6, len(todo))) as ex:
            results = list(ex.map(work, todo))
        for i, (res, refusal, cacheable) in zip(todo, results, strict=True):
            out[i] = (res, refusal)
            if cacheable and refusal is None and res.passed and items[i].key not in ("booked_confirm", "reminder_48h", "reminder_2h"):
                if db.get(LLMCache, keys[i]) is None:
                    db.add(LLMCache(key=keys[i], value=res.as_dict(), created_at=clock.now()))
    return [o for o in out if o is not None]


def persist(
    db: Session,
    conv: Conversation,
    loop: CareLoop,
    r: Rendered,
    res: PipelineResult,
    refusal: str | None,
    kind: str = "text",
    meta: dict[str, Any] | None = None,
) -> Message:
    now = clock.now(db)
    check_id = None
    if conv.language != "en":
        chk = TranslationCheck(
            id=uuid.uuid4(),
            loop_id=loop.id,
            template_key=r.key,
            language=conv.language,
            source_en=res.source_en,
            simplified_en=res.simplified_en,
            translated=res.translated,
            back_translated=res.back_translated,
            judge_score=res.judge_score,
            entity_match=res.entity_match,
            discrepancies=res.discrepancies,
            passed=res.passed,
            fell_back=res.fell_back,
            final_text=res.final_text,
            provider=res.provider,
            created_at=now,
        )
        db.add(chk)
        db.flush()  # the message row references it (no ORM relationship to order inserts)
        check_id = chk.id
        if not res.passed:
            db.add(ReviewItem(item_type="translation_check", item_id=chk.id, loop_id=loop.id, reason="; ".join(res.discrepancies)[:500] or "judge score below threshold"))
            service.record_milestone(db, loop, "translation_qa", "system", f"{r.key} failed QA → {res.final_source}", {"check_id": str(chk.id), "score": res.judge_score})
            if res.final_source == "english_interpreter":
                service.escalate(db, loop, "translation_fail", "system", f"No approved {conv.language} translation for {r.key}")
    if refusal:
        db.add(ReviewItem(item_type="llm_refusal", item_id=check_id, loop_id=loop.id, reason=f"LLM stop_reason={refusal} on {r.key}"))
        service.escalate(db, loop, "llm_refusal", "system", f"LLM {refusal} on {r.key}; approved text used")
    text = res.final_text
    if res.final_source == "english_interpreter" and conv.language != "en":
        offer = find_template(db, loop, "interpreter_offer")
        if offer is not None:
            text = text + "\n\n" + offer.body
    msg = Message(
        conversation_id=conv.id,
        sender="navigator_ai",
        text=text,
        text_en=res.simplified_en,
        template_id=r.template.id if r.template else None,
        translation_check_id=check_id,
        kind=kind,
        meta={
            **(meta or {}),
            "template_key": r.key,
            "qa": {
                "score": round(res.judge_score, 2),
                "passed": res.passed,
                "fell_back": res.fell_back,
                "source": res.final_source,
                "entity_match": res.entity_match,
                "provider": res.provider,
            },
        },
        created_at=now,
    )
    db.add(msg)
    db.flush()
    return msg


def send(
    db: Session,
    conv: Conversation,
    loop: CareLoop,
    keys: list[str | tuple[str, dict[str, Any]]],
    kind_for: dict[str, str] | None = None,
    meta_for: dict[str, dict[str, Any]] | None = None,
) -> list[Message]:
    """Render, check and persist several template messages in order."""
    rendered = []
    for k in keys:
        key, extra = (k, None) if isinstance(k, str) else k
        rendered.append(render(db, loop, key, conv.language, extra))
    results = prepare(db, loop, rendered, conv.language)
    msgs = []
    for r, (res, refusal) in zip(rendered, results, strict=True):
        msgs.append(persist(db, conv, loop, r, res, refusal, (kind_for or {}).get(r.key, "text"), (meta_for or {}).get(r.key)))
    return msgs


def system_message(db: Session, conv: Conversation, text: str, kind: str = "system", meta: dict[str, Any] | None = None) -> Message:
    msg = Message(conversation_id=conv.id, sender="system", text=text, text_en=text, kind=kind, meta=meta or {}, created_at=clock.now(db))
    db.add(msg)
    db.flush()
    return msg
