"""Pydantic v2 request/response models for the API."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str = Field(description="E-mail address or username")
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    username: str | None
    role: str
    display_name: str
    languages: list[str]


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class TransitionIn(BaseModel):
    to_state: str
    reason: str = ""


class AssignIn(BaseModel):
    user_id: uuid.UUID | None = None


class OutreachIn(BaseModel):
    channel: Literal["whatsapp", "sms", "call", "in_person"] | None = None


class OutreachOut(BaseModel):
    conversation_id: str
    token: str
    link: str
    language: str
    state: str


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class BookIn(BaseModel):
    slot_id: uuid.UUID


class LanguageIn(BaseModel):
    language: Literal["en", "ar", "hi", "ur", "ml", "bn", "tl"]


class NoteIn(BaseModel):
    notes: str = ""


class TwinParamsIn(BaseModel):
    horizon_days: int = Field(180, ge=30, le=365)
    n_patients: int = Field(5000, ge=500, le=10000)
    navigators: int = Field(1, ge=1, le=10)
    daily_budget: int = Field(20, ge=1, le=200)
    clinic_capacity_multiplier: float = Field(1.0, ge=0.3, le=3.0)
    extra_evening_friday: bool = False
    extra_language: Literal["ar", "en", "hi", "ur", "ml", "bn", "tl"] | None = None
    cost_sms: float = Field(0.5, ge=0, le=20)
    cost_call: float = Field(25.0, ge=0, le=500)
    cost_visit: float = Field(150.0, ge=0, le=5000)
    seed: int = 42


class TwinRunIn(BaseModel):
    policies: list[Literal["no_outreach", "sms_everyone", "risk_ranked", "wasl_uplift", "wasl_uplift_fair"]] = Field(
        default_factory=lambda: ["no_outreach", "sms_everyone", "risk_ranked", "wasl_uplift", "wasl_uplift_fair"]
    )
    params: TwinParamsIn = Field(default_factory=TwinParamsIn)


class ConsentIn(BaseModel):
    scope: Literal["outreach", "data_for_model", "share_with_clinic"]
    granted: bool
    note: str = ""


class TemplateIn(BaseModel):
    program: Literal["DIABETES", "COLORECTAL", "BREAST", "ANY"]
    severity: Literal["routine", "high", "urgent", "any"]
    key: str = Field(min_length=2, max_length=40)
    body: str = Field(min_length=5, max_length=2000)


class DecideIn(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str = ""


class PreviewIn(BaseModel):
    template_id: uuid.UUID
    language: Literal["en", "ar", "hi", "ur", "ml", "bn", "tl"]
    literacy: int = Field(2, ge=1, le=3)
    persona: Literal["ramesh", "fatima", "joy", "imran", "sara"] = "ramesh"


class Page(BaseModel):
    items: list[Any]
    total: int
    page: int
    size: int
