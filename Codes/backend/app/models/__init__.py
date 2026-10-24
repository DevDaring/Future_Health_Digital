"""Import every model so `Base.metadata` is complete (Alembic and tests rely on this)."""

from app.models.content import (
    ApprovedTranslation,
    ContentTemplate,
    Conversation,
    LLMCache,
    Message,
    TeachBackAttempt,
    TranslationCheck,
)
from app.models.governance import AppSetting, DemoState, FairnessSnapshot, ModelRegistry, ReviewItem, SimRun
from app.models.loops import Appointment, CareLoop, Escalation, LoopEvent, RiskScore, ScreeningEvent
from app.models.people import Clinic, ClinicSlot, Consent, Patient, PatientIdentity, User

__all__ = [
    "AppSetting",
    "Appointment",
    "ApprovedTranslation",
    "CareLoop",
    "Clinic",
    "ClinicSlot",
    "Consent",
    "ContentTemplate",
    "Conversation",
    "DemoState",
    "Escalation",
    "FairnessSnapshot",
    "LLMCache",
    "LoopEvent",
    "Message",
    "ModelRegistry",
    "Patient",
    "PatientIdentity",
    "ReviewItem",
    "RiskScore",
    "ScreeningEvent",
    "SimRun",
    "TeachBackAttempt",
    "TranslationCheck",
    "User",
]
