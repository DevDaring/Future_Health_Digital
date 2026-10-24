"""Barrier-aware smart scheduling (killer feature 5, spec section 9).

    score = w1·shift_compatible + w2·preferred_day + w3·1/(1+distance_km/5)
          + w4·language_match_clinician + w5·evening_or_friday_if_needed − w6·days_until_slot/30

Distances are computed from the person's home area to each clinic, so a near-home
clinic can beat the default one. Every suggestion carries human-readable reasons.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.models import CareLoop, ClinicSlot, Patient
from app.navigator.content import LANG_NAMES

TZ = ZoneInfo("Asia/Dubai")
WEIGHTS = {"shift": 2.0, "day": 1.0, "distance": 1.5, "language": 1.2, "needed": 1.0, "wait": 0.8}

AREA_COORDS: dict[str, tuple[float, float]] = {
    "Al Khalidiyah": (24.4700, 54.3480),
    "Al Reem Island": (24.4980, 54.4050),
    "Mussafah": (24.3550, 54.5050),
    "Khalifa City": (24.4200, 54.5780),
    "Al Shamkha": (24.3700, 54.7000),
    "Baniyas": (24.3000, 54.6300),
    "Mohammed Bin Zayed City": (24.3400, 54.5400),
    "Al Bateen": (24.4550, 54.3350),
    "Al Mushrif": (24.4450, 54.3900),
    "Al Wahda": (24.4700, 54.3750),
    "ICAD": (24.3000, 54.4800),
}
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    # road distance ≈ 1.3 × straight line in a city grid
    return 1.3 * 2 * 6371 * math.asin(math.sqrt(h))


def local(dt: datetime) -> datetime:
    return clock.as_utc(dt).astimezone(TZ)


def format_slot(dt: datetime) -> str:
    d = local(dt)
    return d.strftime("%a %d %b, %H:%M")


@dataclass
class SlotSuggestion:
    slot: ClinicSlot
    score: float
    distance_km: float
    reasons: list[str]

    def as_dict(self) -> dict[str, Any]:
        d = local(self.slot.start_at)
        return {
            "slot_id": str(self.slot.id),
            "clinic_id": str(self.slot.clinic_id),
            "clinic_name": self.slot.clinic.name,
            "clinic_area": self.slot.clinic.area,
            "start_at": clock.as_utc(self.slot.start_at).isoformat(),
            "local_label": format_slot(self.slot.start_at),
            "weekday": DAY_NAMES[d.weekday()],
            "clinician_language": self.slot.clinician_language,
            "distance_km": round(self.distance_km, 1),
            "score": round(self.score, 3),
            "match_reasons": self.reasons,
        }


def _is_evening(d: datetime) -> bool:
    return d.hour >= 17


def shift_compatible(patient: Patient, d: datetime) -> tuple[bool, str]:
    wd = DAY_NAMES[d.weekday()]
    weekend = wd in ("Fri", "Sat", "Sun")
    if patient.no_free_weekdays:
        ok = wd in (patient.preferred_days or ["Fri"])
        return ok, f"{wd} — your day off" if ok else ""
    if patient.shift_pattern == "night":
        # Night workers sleep in the morning: evenings fit, as do weekend afternoons.
        if _is_evening(d):
            return True, ("Friday evening — fits night shift" if wd == "Fri" else "Evening — fits night shift")
        ok = wd in ("Fri", "Sat") and d.hour >= 13
        return ok, f"{wd} afternoon — fits night shift" if ok else ""
    if patient.shift_pattern == "rotating":
        ok = _is_evening(d) or weekend
        return ok, "Outside rotating-shift hours" if ok else ""
    if patient.shift_pattern == "split":
        ok = 13 <= d.hour < 16 or weekend
        return ok, "Fits the break in a split shift" if ok else ""
    ok = patient.occupation_type in ("office", "healthcare") or _is_evening(d) or weekend
    return ok, "Outside working hours" if ok and (_is_evening(d) or weekend) else ""


def suggest_slots(db: Session, loop: CareLoop, k: int = 3) -> list[SlotSuggestion]:
    patient = loop.patient
    now = clock.now(db)
    q = (
        select(ClinicSlot)
        .where(
            ClinicSlot.program == loop.screening.program,
            ClinicSlot.is_booked.is_(False),
            ClinicSlot.start_at > now + timedelta(hours=12),
            ClinicSlot.start_at < now + timedelta(days=30),
        )
        .order_by(ClinicSlot.start_at)
    )
    home = AREA_COORDS.get(patient.home_area, AREA_COORDS["Al Wahda"])
    needs_evening_friday = patient.shift_pattern in ("night", "rotating") or patient.no_free_weekdays
    scored: list[SlotSuggestion] = []
    for slot in db.scalars(q):
        d = local(slot.start_at)
        wd = DAY_NAMES[d.weekday()]
        clinic = slot.clinic
        dist = haversine_km(home, (clinic.lat, clinic.lon))
        reasons: list[str] = []
        compat, why = shift_compatible(patient, d)
        if why:
            reasons.append(why)
        pref = wd in (patient.preferred_days or [])
        if pref and not why.startswith(wd):
            reasons.append(f"{wd} is a preferred day")
        lang_match = slot.clinician_language == patient.preferred_language
        if lang_match and patient.preferred_language != "en":
            reasons.append(f"{LANG_NAMES.get(slot.clinician_language, slot.clinician_language)}-speaking clinician")
        reasons.append(f"{dist:.0f} km from home")
        needed = needs_evening_friday and (_is_evening(d) or wd == "Fri")
        days_until = max(0.0, (clock.as_utc(slot.start_at) - now).total_seconds() / 86400)
        score = (
            WEIGHTS["shift"] * compat
            + WEIGHTS["day"] * pref
            + WEIGHTS["distance"] * (1 / (1 + dist / 5))
            + WEIGHTS["language"] * lang_match
            + WEIGHTS["needed"] * needed
            - WEIGHTS["wait"] * days_until / 30
        )
        if loop.screening.severity == "urgent" and days_until > 7:
            score -= 2.0  # urgent results must be seen within the SLA
        scored.append(SlotSuggestion(slot=slot, score=score, distance_km=dist, reasons=reasons))
    scored.sort(key=lambda s: (-s.score, s.slot.start_at))
    # Offer variety: at most one suggestion per clinic per day.
    out: list[SlotSuggestion] = []
    seen: set[tuple[str, str]] = set()
    for s in scored:
        key = (str(s.slot.clinic_id), local(s.slot.start_at).date().isoformat())
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= k:
            break
    return out
