"""Users, clinics, slots, patients, identity and consent.

Identity (`patient_identity`) is deliberately a separate table from clinical data
(`patients`): only the PII firewall and role-masked serializers read it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, StrList
from app.models.base import IdMixin, TimestampMixin


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))  # admin | coordinator | clinician | navigator
    display_name: Mapped[str] = mapped_column(String(120))
    languages: Mapped[list[str]] = mapped_column(StrList, default=list)


class Clinic(IdMixin, TimestampMixin, Base):
    __tablename__ = "clinics"
    name: Mapped[str] = mapped_column(String(160))
    area: Mapped[str] = mapped_column(String(80))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    languages_spoken: Mapped[list[str]] = mapped_column(StrList, default=list)
    evening_hours: Mapped[bool] = mapped_column(Boolean, default=False)
    friday_hours: Mapped[bool] = mapped_column(Boolean, default=False)


class ClinicSlot(IdMixin, TimestampMixin, Base):
    __tablename__ = "clinic_slots"
    clinic_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clinics.id", ondelete="CASCADE"))
    program: Mapped[str] = mapped_column(String(20))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_booked: Mapped[bool] = mapped_column(Boolean, default=False)
    clinician_language: Mapped[str] = mapped_column(String(5))
    clinic: Mapped[Clinic] = relationship(lazy="joined")


class Patient(IdMixin, TimestampMixin, Base):
    """Pseudonymous clinical/social profile. No direct identifiers here."""

    __tablename__ = "patients"
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # pseudonymous display id
    persona: Mapped[str | None] = mapped_column(String(20), nullable=True)
    age: Mapped[int] = mapped_column(Integer)
    sex: Mapped[str] = mapped_column(String(1))
    nationality_group: Mapped[str] = mapped_column(String(30))
    preferred_language: Mapped[str] = mapped_column(String(5))
    literacy_level: Mapped[int] = mapped_column(Integer)
    occupation_type: Mapped[str] = mapped_column(String(20))
    shift_pattern: Mapped[str] = mapped_column(String(10))
    preferred_days: Mapped[list[str]] = mapped_column(StrList, default=list)
    home_area: Mapped[str] = mapped_column(String(80))
    distance_km: Mapped[float] = mapped_column(Float)
    insurance_tier: Mapped[str] = mapped_column(String(10))
    prior_no_shows: Mapped[int] = mapped_column(Integer, default=0)
    has_smartphone: Mapped[bool] = mapped_column(Boolean, default=True)
    preferred_channel: Mapped[str] = mapped_column(String(12))
    no_free_weekdays: Mapped[bool] = mapped_column(Boolean, default=False)


class PatientIdentity(IdMixin, TimestampMixin, Base):
    __tablename__ = "patient_identity"
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("patients.id", ondelete="CASCADE"), unique=True)
    full_name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str] = mapped_column(String(30))
    emirates_id_masked: Mapped[str] = mapped_column(String(30))


class Consent(IdMixin, TimestampMixin, Base):
    __tablename__ = "consents"
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    scope: Mapped[str] = mapped_column(String(30))  # outreach | data_for_model | share_with_clinic
    granted: Mapped[bool] = mapped_column(Boolean)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    channel: Mapped[str] = mapped_column(String(20), default="in_person")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


Index("ix_consents_patient_scope", Consent.patient_id, Consent.scope)
