"""Screening events, care loops, the hash-chained loop event log, scores, appointments
and escalations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, JSONType
from app.models.base import IdMixin, TimestampMixin
from app.models.people import ClinicSlot, Patient


class ScreeningEvent(IdMixin, TimestampMixin, Base):
    __tablename__ = "screening_events"
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    program: Mapped[str] = mapped_column(String(20))  # DIABETES | COLORECTAL | BREAST
    test_code: Mapped[str] = mapped_column(String(20))  # HBA1C | FIT | BIRADS
    value_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(60), nullable=True)
    severity: Mapped[str] = mapped_column(String(10))  # routine | high | urgent
    category: Mapped[str] = mapped_column(String(40), default="")  # e.g. prediabetes, recall
    resulted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(20), default="synthetic")


class CareLoop(IdMixin, TimestampMixin, Base):
    __tablename__ = "care_loops"
    screening_event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("screening_events.id", ondelete="CASCADE"), unique=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    state: Mapped[str] = mapped_column(String(20))
    escalated_from: Mapped[str | None] = mapped_column(String(20), nullable=True)
    breached: Mapped[bool] = mapped_column(Boolean, default=False)
    sla_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_dropoff: Mapped[float | None] = mapped_column(Float, nullable=True)
    uplift: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    understood_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    navigator_paused: Mapped[bool] = mapped_column(Boolean, default=False)  # red flag: AI stops until ack
    demo_fault: Mapped[str | None] = mapped_column(String(40), nullable=True)

    patient: Mapped[Patient] = relationship(lazy="joined")
    screening: Mapped[ScreeningEvent] = relationship(lazy="joined")


Index("ix_care_loops_state", CareLoop.state)
Index("ix_care_loops_sla_due_at", CareLoop.sla_due_at)
Index("ix_care_loops_priority_desc", CareLoop.priority_score.desc())


class LoopEvent(IdMixin, Base):
    """Append-only, SHA-256 hash-chained. Each row links to the previous row of the same
    loop (`prev_hash`) and of the global chain (`global_prev_hash`)."""

    __tablename__ = "loop_events"
    seq: Mapped[int] = mapped_column(Integer, unique=True)  # global order (unique: one chain)
    loop_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("care_loops.id", ondelete="CASCADE"))
    from_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_state: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(80))  # user:<email> | system | patient
    reason: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
    global_prev_hash: Mapped[str] = mapped_column(String(64))
    global_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


Index("ix_loop_events_loop_created", LoopEvent.loop_id, LoopEvent.created_at)


class RiskScore(IdMixin, Base):
    __tablename__ = "risk_scores"
    loop_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("care_loops.id", ondelete="CASCADE"), index=True)
    model_version: Mapped[str] = mapped_column(String(40))
    p_dropoff: Mapped[float] = mapped_column(Float)
    p_return_if_contacted: Mapped[float] = mapped_column(Float)
    p_return_if_not: Mapped[float] = mapped_column(Float)
    uplift: Mapped[float] = mapped_column(Float)
    shap_top: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    counterfactuals: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Appointment(IdMixin, TimestampMixin, Base):
    __tablename__ = "appointments"
    loop_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("care_loops.id", ondelete="CASCADE"), index=True)
    slot_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clinic_slots.id"))
    status: Mapped[str] = mapped_column(String(12), default="booked")
    match_reasons: Mapped[list[str]] = mapped_column(JSONType, default=list)
    slot: Mapped[ClinicSlot] = relationship(lazy="joined")


class Escalation(IdMixin, TimestampMixin, Base):
    __tablename__ = "escalations"
    loop_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("care_loops.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(10), default="open")
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
