"""FHIR R4 mappers (spec killer feature 12): Observation, ServiceRequest, Task and
Appointment out; a Bundle of Patient + Observation in (creates a new care loop).

Coding notes (verify with an informatics lead before real exchange, e.g. Malaffi):
* HbA1c: LOINC 4548-4 "Hemoglobin A1c/Hemoglobin.total in Blood".
* FIT: LOINC 29771-3 "Hemoglobin.gastrointestinal.lower [Presence] in Stool by Immunoassay".
* BI-RADS: a local code system is used here on purpose; map to the code your HIE expects.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app import clock
from app.config import get_settings
from app.loop_engine import audit
from app.models import Appointment, CareLoop, Consent, Patient, PatientIdentity, ScreeningEvent
from app.synth.population import classify

LOINC = "http://loinc.org"
LOCAL = "https://wasl.demo/fhir/CodeSystem/screening"
CODES = {
    "HBA1C": {"system": LOINC, "code": "4548-4", "display": "Hemoglobin A1c/Hemoglobin.total in Blood"},
    "FIT": {"system": LOINC, "code": "29771-3", "display": "Hemoglobin.gastrointestinal.lower [Presence] in Stool by Immunoassay"},
    "BIRADS": {"system": LOCAL, "code": "birads-assessment", "display": "Mammogram BI-RADS assessment category"},
}
PROGRAM_OF = {"HBA1C": "DIABETES", "FIT": "COLORECTAL", "BIRADS": "BREAST"}
TASK_STATUS = {
    "RESULT_RECEIVED": "requested", "NOTIFIED": "requested", "ENGAGED": "in-progress", "UNDERSTOOD": "in-progress",
    "BOOKED": "accepted", "ATTENDED": "completed", "CLOSED": "completed", "UNREACHABLE": "on-hold", "DECLINED": "rejected",
    "NO_SHOW": "in-progress", "ESCALATED": "on-hold", "BREACHED": "in-progress",
}


def _iso(dt: datetime) -> str:
    return clock.as_utc(dt).isoformat()


def observation(se: ScreeningEvent, patient: Patient) -> dict[str, Any]:
    obs: dict[str, Any] = {
        "resourceType": "Observation",
        "id": str(se.id),
        "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "laboratory" if se.test_code != "BIRADS" else "imaging"}]}],
        "code": {"coding": [CODES[se.test_code]], "text": se.test_code},
        "subject": {"reference": f"Patient/{patient.id}", "display": patient.code},
        "effectiveDateTime": _iso(se.resulted_at),
        "interpretation": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                                        "code": "A" if se.severity != "urgent" else "AA"}], "text": se.category}],
    }
    if se.test_code == "HBA1C" and se.value_numeric is not None:
        obs["valueQuantity"] = {"value": se.value_numeric, "unit": "%", "system": "http://unitsofmeasure.org", "code": "%"}
    elif se.test_code == "BIRADS" and se.value_numeric is not None:
        obs["valueCodeableConcept"] = {"text": se.value_text or f"BI-RADS {int(se.value_numeric)}"}
    else:
        obs["valueCodeableConcept"] = {"text": se.value_text or "positive"}
    return obs


def service_request(loop: CareLoop) -> dict[str, Any]:
    se = loop.screening
    return {
        "resourceType": "ServiceRequest",
        "id": f"sr-{loop.id}",
        "status": "active" if loop.state not in ("CLOSED", "DECLINED") else ("completed" if loop.state == "CLOSED" else "revoked"),
        "intent": "order",
        "priority": {"urgent": "urgent", "high": "asap"}.get(se.severity, "routine"),
        "code": {"text": f"Follow-up after abnormal {se.test_code} ({se.category})"},
        "subject": {"reference": f"Patient/{loop.patient_id}"},
        "reasonReference": [{"reference": f"Observation/{se.id}"}],
        "occurrencePeriod": {"start": _iso(se.resulted_at), "end": _iso(loop.sla_due_at)},
    }


def task(loop: CareLoop) -> dict[str, Any]:
    return {
        "resourceType": "Task",
        "id": str(loop.id),
        "status": TASK_STATUS.get(loop.state, "requested"),
        "businessStatus": {"text": loop.state},
        "intent": "order",
        "priority": {"urgent": "urgent", "high": "asap"}.get(loop.screening.severity, "routine"),
        "description": "Close the screening-to-care loop",
        "focus": {"reference": f"ServiceRequest/sr-{loop.id}"},
        "for": {"reference": f"Patient/{loop.patient_id}"},
        "authoredOn": _iso(loop.created_at),
        "restriction": {"period": {"end": _iso(loop.sla_due_at)}},
        "input": [{"type": {"text": "uplift"}, "valueDecimal": round(loop.uplift or 0, 4)},
                  {"type": {"text": "p_dropoff"}, "valueDecimal": round(loop.risk_dropoff or 0, 4)}],
    }


def appointment(ap: Appointment, loop: CareLoop) -> dict[str, Any]:
    slot = ap.slot
    status = {"booked": "booked", "attended": "fulfilled", "no_show": "noshow", "cancelled": "cancelled"}.get(ap.status, "booked")
    return {
        "resourceType": "Appointment",
        "id": str(ap.id),
        "status": status,
        "description": f"Follow-up visit ({loop.screening.program})",
        "start": _iso(slot.start_at),
        "end": _iso(slot.end_at),
        "basedOn": [{"reference": f"ServiceRequest/sr-{loop.id}"}],
        "participant": [
            {"actor": {"reference": f"Patient/{loop.patient_id}"}, "status": "accepted"},
            {"actor": {"display": slot.clinic.name}, "status": "accepted"},
        ],
        "comment": "; ".join(ap.match_reasons or []),
    }


def import_bundle(db: Session, bundle: dict[str, Any]) -> list[CareLoop]:
    """Import Patient + Observation entries. Each abnormal Observation becomes a loop."""
    if bundle.get("resourceType") != "Bundle":
        raise ValueError("resourceType must be Bundle")
    entries = [e.get("resource", {}) for e in bundle.get("entry", [])]
    patients: dict[str, Patient] = {}
    for res in entries:
        if res.get("resourceType") != "Patient":
            continue
        ext = {e.get("url", "").rsplit("/", 1)[-1]: e for e in res.get("extension", [])}
        lang = (res.get("communication") or [{}])[0].get("language", {}).get("coding", [{}])[0].get("code", "en")[:2]
        birth = res.get("birthDate", "1980-01-01")
        age = max(18, clock.now(db).year - int(birth[:4]))
        pid = uuid.uuid4()
        p = Patient(
            id=pid, code=f"WASL-F{str(pid)[:5].upper()}", age=age, sex="F" if res.get("gender") == "female" else "M",
            nationality_group=ext.get("nationality-group", {}).get("valueString", "Other"), preferred_language=lang,
            literacy_level=2, occupation_type=ext.get("occupation", {}).get("valueString", "office"),
            shift_pattern=ext.get("shift-pattern", {}).get("valueString", "day"), preferred_days=["Mon", "Tue", "Wed", "Thu"],
            home_area=(res.get("address") or [{}])[0].get("district", "Al Wahda"), distance_km=10.0,
            insurance_tier=ext.get("insurance-tier", {}).get("valueString", "enhanced"), prior_no_shows=0, has_smartphone=True,
            preferred_channel="whatsapp", no_free_weekdays=False,
        )
        db.add(p)
        db.flush()
        name = res.get("name", [{}])[0]
        full = " ".join([*(name.get("given") or []), name.get("family", "")]).strip() or "Imported Patient"
        phone = next((t.get("value") for t in res.get("telecom", []) if t.get("system") == "phone"), "+971 50 000 0000")
        db.add(PatientIdentity(patient_id=pid, full_name=full, phone=phone, emirates_id_masked="784-****-*******-*"))
        db.add(Consent(patient_id=pid, scope="outreach", granted=True, granted_at=clock.now(db), channel="fhir_import"))
        patients[f"Patient/{res.get('id')}"] = p
    loops: list[CareLoop] = []
    for res in entries:
        if res.get("resourceType") != "Observation":
            continue
        p = patients.get(res.get("subject", {}).get("reference", ""))
        if p is None:
            continue
        coding = res.get("code", {}).get("coding", [{}])[0]
        test = next((k for k, v in CODES.items() if v["code"] == coding.get("code")), None)
        if test is None:
            continue
        program = PROGRAM_OF[test]
        value_num = res.get("valueQuantity", {}).get("value")
        value_text = res.get("valueCodeableConcept", {}).get("text") or res.get("valueString")
        if test == "BIRADS" and value_text:
            digits = [c for c in value_text if c.isdigit()]
            value_num = float(digits[0]) if digits else None
        sev_cat = classify(program, value_num, value_text)
        if sev_cat is None:
            continue  # normal result: no loop
        resulted = datetime.fromisoformat(res.get("effectiveDateTime", datetime.now(UTC).isoformat()).replace("Z", "+00:00"))
        se = ScreeningEvent(patient_id=p.id, program=program, test_code=test, value_numeric=value_num, value_text=value_text,
                            severity=sev_cat[0], category=sev_cat[1], resulted_at=resulted, source="fhir_import")
        db.add(se)
        db.flush()
        loop = CareLoop(screening_event_id=se.id, patient_id=p.id, state="RESULT_RECEIVED",
                        sla_due_at=resulted + timedelta(days=get_settings().sla_days(sev_cat[0])))
        db.add(loop)
        db.flush()
        audit.append_event(db, loop.id, None, "RESULT_RECEIVED", "system:fhir", f"Imported Observation {res.get('id')}", {"source": "fhir"}, clock.now(db))
        loops.append(loop)
    db.flush()
    return loops
