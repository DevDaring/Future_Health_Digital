"""Seed the database: users, clinics + 30 days of slots, approved content and fixture
translations, the synthetic population with consents, abnormal results and care loops
(with a realistic as-is history), and the five demo personas.

    python -m app.synth.seed [--seed 42] [--reset]

Determinism: all clinical/social data, results and loop histories come from one seeded
RNG. Timestamps are anchored to the (simulated) current time, so the checksum covers
everything *except* absolute times (it uses day offsets instead).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import clock
from app.config import get_settings
from app.db import Base
from app.loop_engine import audit
from app.loop_engine.sla import check_breaches
from app.models import (
    ApprovedTranslation,
    AppSetting,
    CareLoop,
    Clinic,
    ClinicSlot,
    Consent,
    ContentTemplate,
    DemoState,
    Escalation,
    Patient,
    PatientIdentity,
    ScreeningEvent,
    User,
)
from app.navigator.content import LANGS, fixture_translations, templates_fixture
from app.security import hash_password
from app.synth.behaviour import SMS_DEFAULT, baseline_logit, effect_logit, sigmoid
from app.synth.personas import CLINICS, NAMES, PERSONAS, USERS
from app.synth.population import classify, draw_abnormal_results, generate_population

log = logging.getLogger("wasl.seed")
NS = uuid.UUID("6f1c2b52-8f3e-4a55-9d0e-0a5a51a00042")
TZ = ZoneInfo("Asia/Dubai")
DEMO_PASSWORD = "demo1234"


def did(kind: str, key: Any) -> uuid.UUID:
    return uuid.uuid5(NS, f"{kind}:{key}")


# ----------------------------------------------------------------------- reset

def wipe(db: Session) -> None:
    """Delete all rows (FK-safe). Keeps the schema.

    DELETE rather than TRUNCATE on purpose: TRUNCATE takes ACCESS EXCLUSIVE locks table by
    table and deadlocks with the dashboard's live polling during a Judge Mode reset.
    DELETE only takes row locks, so readers keep seeing the old data until we commit.
    """
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(delete(table))
    clock._cache.clear()
    db.flush()


# ---------------------------------------------------------------------- pieces

def seed_users(db: Session) -> dict[str, User]:
    out = {}
    hashed_demo = hash_password(DEMO_PASSWORD)
    for u in USERS:
        user = User(
            id=did("user", u["email"]),
            email=u["email"],
            username=u.get("username"),
            password_hash=hash_password(u["password"]) if u.get("password") else hashed_demo,
            role=u["role"],
            display_name=u["display_name"],
            languages=u["languages"],
        )
        db.add(user)
        out[u["email"]] = user
    db.flush()
    return out


def seed_clinics_and_slots(db: Session, now: datetime) -> list[Clinic]:
    clinics = []
    for c in CLINICS:
        clinic = Clinic(
            id=did("clinic", c["name"]),
            name=c["name"],
            area=c["area"],
            lat=c["lat"],
            lon=c["lon"],
            languages_spoken=c["languages_spoken"],
            evening_hours=c["evening_hours"],
            friday_hours=c["friday_hours"],
        )
        db.add(clinic)
        clinics.append((clinic, c))
    db.flush()
    start_day = now.astimezone(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    slots = []
    for clinic, c in clinics:
        n = 0
        for d in range(1, 31):
            day = start_day + timedelta(days=d)
            wd = day.strftime("%a")
            times: list[tuple[int, int]] = []
            if wd in ("Mon", "Tue", "Wed", "Thu"):
                times += [(h, m) for h in range(8, 12) for m in (0, 30)] + [(14, 0), (14, 30), (15, 30)]
                if c["evening_hours"]:
                    times += [(17, 30), (18, 0), (18, 30), (19, 30), (20, 0)]
            elif wd == "Fri":
                times += [(8, 0), (8, 30), (9, 30), (10, 30)]
                if c["friday_hours"]:
                    times += [(14, 30), (16, 0), (17, 30), (18, 0), (18, 30), (19, 30)]
            elif wd in c["weekend"]:
                times += [(9, 0), (9, 30), (10, 30), (11, 0), (12, 0)]
            for h, m in times:
                start = day.replace(hour=h, minute=m).astimezone(UTC)
                lang = c["languages_spoken"][n % len(c["languages_spoken"])]
                program = c["programs"][n % len(c["programs"])]
                slots.append(
                    ClinicSlot(
                        clinic_id=clinic.id, program=program, start_at=start, end_at=start + timedelta(minutes=20),
                        is_booked=False, clinician_language=lang,
                    )
                )
                n += 1
    db.add_all(slots)
    db.flush()
    return [c for c, _ in clinics]


def seed_content(db: Session, now: datetime) -> None:
    tf = templates_fixture()
    approved_by = tf["approved_by"]
    rows: list[tuple[str, str, str, str]] = [("ANY", "any", k, v) for k, v in tf["generic"].items()]
    for prog, sevs in tf["programs"].items():
        for sev, keys in sevs.items():
            rows += [(prog, sev, k, v) for k, v in keys.items()]
    for prog, sev, key, body in rows:
        t = ContentTemplate(
            id=did("template", f"{prog}.{sev}.{key}"), program=prog, severity=sev, key=key, language="en", body=body,
            approved_by=approved_by, approved_at=now, version=1, status="approved",
        )
        db.add(t)
        db.flush()
        for lang in LANGS:
            if lang == "en":
                continue
            tr = fixture_translations(lang).get(f"{prog}.{sev}.{key}")
            if tr:
                db.add(ApprovedTranslation(template_id=t.id, language=lang, body=tr, approved_by=f"{approved_by} + medical translator (demo)", approved_at=now))
    db.flush()


def _identity(rng: np.random.Generator, nat: str, sex: str) -> tuple[str, str, str]:
    first, last = NAMES.get(nat, NAMES["Other"])
    name = f"{first[int(rng.integers(len(first)))]} {last[int(rng.integers(len(last)))]}"
    phone = f"+971 5{int(rng.integers(0, 9))} {int(rng.integers(100, 999))} {int(rng.integers(1000, 9999))}"
    eid = f"784-{int(rng.integers(1955, 2003))}-{int(rng.integers(1000000, 9999999))}-{int(rng.integers(0, 9))}"
    return name, phone, eid


def mask_eid(eid: str) -> str:
    parts = eid.split("-")
    return f"{parts[0]}-****-*****{parts[2][-2:]}-{parts[3]}" if len(parts) == 4 else "784-****-*******-*"


def seed_population(db: Session, seed: int, n: int, now: datetime) -> pd.DataFrame:
    pop = generate_population(n, seed)
    rng = np.random.default_rng(seed + 1)
    patients, idents, consents = [], [], []
    for row in pop.itertuples(index=False):
        pid = did("patient", row.idx)
        patients.append(
            Patient(
                id=pid, code=f"WASL-P{row.idx + 1:05d}", age=row.age, sex=row.sex, nationality_group=row.nationality_group,
                preferred_language=row.preferred_language, literacy_level=row.literacy_level, occupation_type=row.occupation_type,
                shift_pattern=row.shift_pattern, preferred_days=row.preferred_days, home_area=row.home_area,
                distance_km=row.distance_km, insurance_tier=row.insurance_tier, prior_no_shows=row.prior_no_shows,
                has_smartphone=row.has_smartphone, preferred_channel=row.preferred_channel, no_free_weekdays=row.no_free_weekdays,
            )
        )
        name, phone, eid = _identity(rng, row.nationality_group, row.sex)
        idents.append(PatientIdentity(patient_id=pid, full_name=name, phone=phone, emirates_id_masked=mask_eid(eid)))
        granted_at = now - timedelta(days=int(rng.integers(150, 900)))
        for scope, p in (("outreach", 0.95), ("data_for_model", 0.9), ("share_with_clinic", 0.96)):
            g = bool(rng.random() < p)
            consents.append(Consent(patient_id=pid, scope=scope, granted=g, granted_at=granted_at if g else None, channel="registration"))
    db.add_all(patients)
    db.flush()
    db.add_all(idents)
    db.add_all(consents)
    db.flush()
    pop["patient_id"] = [did("patient", i) for i in pop["idx"]]
    return pop


def _days(dt: datetime, now: datetime) -> float:
    return (now - dt).total_seconds() / 86400


def seed_loops(db: Session, pop: pd.DataFrame, seed: int, now: datetime, head: audit.ChainHead) -> list[dict[str, Any]]:
    """Abnormal results + loops whose state reflects the as-is process (bilingual SMS only)."""
    s = get_settings()
    rng = np.random.default_rng(seed + 2)
    results = draw_abnormal_results(pop, rng)
    res = pd.DataFrame(results).merge(pop, on="idx", how="left")
    res["days_since_result"] = 0
    p_as_is = sigmoid(baseline_logit(res) + effect_logit(res, SMS_DEFAULT.channel, False, "none", False))
    summary = []
    screenings: list[ScreeningEvent] = []
    loops: list[CareLoop] = []
    pending_events: list[tuple[Any, ...]] = []
    for i, r in enumerate(res.itertuples(index=False)):
        age_days = float(rng.uniform(0.5, 120))
        resulted = now - timedelta(days=age_days)
        se_id = did("screening", f"{r.idx}:{r.program}")
        screenings.append(
            ScreeningEvent(
                id=se_id, patient_id=r.patient_id, program=r.program, test_code=r.test_code, value_numeric=r.value_numeric,
                value_text=r.value_text, severity=r.severity, category=r.category, resulted_at=resulted, source="synthetic",
            )
        )
        loop_id = did("loop", f"{r.idx}:{r.program}")
        sla_due = resulted + timedelta(days=s.sla_days(r.severity))
        events: list[tuple[float, str]] = [(0.0, "RESULT_RECEIVED")]
        t_notify = float(rng.uniform(0.3, 3))
        reachable = rng.random() < 0.9
        returns = rng.random() < p_as_is[i]
        t_return = 2 + float(rng.exponential(18))
        disengaged = rng.random()
        if age_days > t_notify:
            if not reachable:
                if age_days > t_notify + 5:
                    events.append((t_notify + 5, "UNREACHABLE"))
            else:
                events.append((t_notify, "NOTIFIED"))
                if returns:
                    t_eng = max(t_notify + 0.2, t_return - 6)
                    t_book = max(t_eng + 0.1, t_return - 5)
                    for t, st in ((t_eng, "ENGAGED"), (t_book, "BOOKED"), (t_return, "ATTENDED"), (t_return + 2, "CLOSED")):
                        if age_days > t:
                            events.append((t, st))
                elif disengaged < 0.35:
                    t_eng = t_notify + float(rng.uniform(1, 10))
                    if age_days > t_eng:
                        events.append((t_eng, "ENGAGED"))
                        if disengaged < 0.03 and age_days > t_eng + 2:
                            events.append((t_eng + 2, "DECLINED"))
        state = events[-1][1]
        loop = CareLoop(
            id=loop_id, screening_event_id=se_id, patient_id=r.patient_id, state=state, sla_due_at=sla_due,
            last_contact_at=resulted + timedelta(days=t_notify) if len(events) > 1 else None,
            closed_at=resulted + timedelta(days=events[-1][0]) if state in ("CLOSED", "DECLINED") else None,
        )
        loops.append(loop)
        prev = None
        for t, st in events:
            reason = {
                "RESULT_RECEIVED": f"{r.test_code} result received ({r.category})",
                "NOTIFIED": "Standard bilingual (en/ar) SMS notification",
                "ENGAGED": "Patient replied / opened message",
                "BOOKED": "Booked via call centre",
                "ATTENDED": "Attended follow-up",
                "CLOSED": "Follow-up completed",
                "UNREACHABLE": "No response after 5 days",
                "DECLINED": "Informed refusal recorded",
            }[st]
            payload = {"informed_refusal": True} if st == "DECLINED" else {}
            pending_events.append((loop_id, prev, st, "system" if st != "BOOKED" else "user:callcentre", reason, payload, resulted + timedelta(days=t)))
            prev = st
        summary.append({"idx": int(r.idx), "program": r.program, "state": state, "age": round(age_days, 2), "value": r.value_numeric})
    # Insert in FK order: results, loops, then the hash-chained events.
    db.add_all(screenings)
    db.flush()
    db.add_all(loops)
    db.flush()
    for ev in pending_events:
        audit.append_event(db, *ev, head=head)
    db.flush()
    return summary


def seed_personas(db: Session, now: datetime, head: audit.ChainHead, nav: User) -> None:
    s = get_settings()
    for k, p in enumerate(PERSONAS):
        pid = did("persona", p["persona"])
        db.add(Patient(id=pid, code=f"WASL-P{90001 + k:05d}", persona=p["persona"], **p["patient"]))
        db.flush()
        db.add(PatientIdentity(patient_id=pid, full_name=p["full_name"], phone=p["phone"], emirates_id_masked=mask_eid(p["eid"])))
        for scope in ("outreach", "data_for_model", "share_with_clinic"):
            db.add(Consent(patient_id=pid, scope=scope, granted=True, granted_at=now - timedelta(days=400), channel="registration"))
        r = p["result"]
        severity, category = classify(r["program"], r["value_numeric"], r["value_text"])  # type: ignore[misc]
        resulted = now - timedelta(days=p["days_ago"], hours=3)
        se_id = did("screening", f"persona:{p['persona']}")
        db.add(ScreeningEvent(id=se_id, patient_id=pid, severity=severity, category=category, resulted_at=resulted, source="synthetic", **r))
        db.flush()
        loop_id = did("loop", f"persona:{p['persona']}")
        db.add(
            CareLoop(id=loop_id, screening_event_id=se_id, patient_id=pid, state="RESULT_RECEIVED",
                     sla_due_at=resulted + timedelta(days=s.sla_days(severity)), assigned_to=nav.id, demo_fault=p["demo_fault"])
        )
        db.flush()
        audit.append_event(db, loop_id, None, "RESULT_RECEIVED", "system", f"{r['test_code']} result received ({category})", {}, resulted, head)
    db.flush()


def checksum(pop: pd.DataFrame, summary: list[dict[str, Any]]) -> str:
    cols = ["idx", "age", "sex", "nationality_group", "preferred_language", "literacy_level", "occupation_type", "shift_pattern",
            "distance_km", "insurance_tier", "prior_no_shows", "preferred_channel"]
    payload = json.dumps([pop[cols].astype(str).values.tolist(), summary], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def seed_all(db: Session, seed: int | None = None, n: int | None = None) -> dict[str, Any]:
    s = get_settings()
    seed = s.seed if seed is None else seed
    n = n or s.population_size
    wipe(db)
    db.add(AppSetting(key="clock_offset_seconds", value="0"))
    db.flush()
    now = clock.now(db)
    users = seed_users(db)
    seed_clinics_and_slots(db, now)
    seed_content(db, now)
    pop = seed_population(db, seed, n, now)
    head = audit.ChainHead()
    head.seq = 0
    summary = seed_loops(db, pop, seed, now, head)
    seed_personas(db, now, head, users["nav@wasl.demo"])

    # Assign a slice of open loops to the navigator (RBAC: navigators see assigned only).
    rng = np.random.default_rng(seed + 3)
    open_ids = list(db.scalars(select(CareLoop.id).where(CareLoop.state.notin_(["CLOSED", "DECLINED", "ATTENDED"])).order_by(CareLoop.id)))
    for lid in rng.choice(open_ids, size=min(150, len(open_ids)), replace=False):
        db.get(CareLoop, lid).assigned_to = users["nav@wasl.demo"].id  # type: ignore[union-attr]
    db.flush()

    check_breaches(db)
    # Older breaches were handled before today: keep only the last 5 days' breaches open.
    for esc in db.scalars(select(Escalation).where(Escalation.reason == "sla_breach")):
        loop = db.get(CareLoop, esc.loop_id)
        if loop is not None and _days(clock.as_utc(loop.sla_due_at), now) > 5:
            esc.status = "ack"
    counts = {
        "patients": int(db.scalar(select(func.count(Patient.id))) or 0),
        "loops": int(db.scalar(select(func.count(CareLoop.id))) or 0),
        "screening_events": int(db.scalar(select(func.count(ScreeningEvent.id))) or 0),
        "slots": int(db.scalar(select(func.count(ClinicSlot.id))) or 0),
        "templates": int(db.scalar(select(func.count(ContentTemplate.id))) or 0),
        "translations": int(db.scalar(select(func.count(ApprovedTranslation.id))) or 0),
        "loop_events": audit.event_count(db),
    }
    cs = checksum(pop, summary)
    db.add(DemoState(id=1, seed=seed, checksum=cs, counts=counts, seeded_at=datetime.now(UTC)))
    db.flush()
    return {"seed": seed, "checksum": cs, "counts": counts}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from app.db import session_scope

    with session_scope() as db:
        info = seed_all(db, args.seed)
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
