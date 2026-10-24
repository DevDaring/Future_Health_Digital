"""Governance tables: review queue, model registry, twin runs, fairness snapshots and
small key/value app settings (e.g. the simulated clock offset)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, JSONType
from app.models.base import IdMixin, TimestampMixin


class ReviewItem(IdMixin, TimestampMixin, Base):
    __tablename__ = "review_queue"
    item_type: Mapped[str] = mapped_column(String(30))  # translation_check | teach_back | refusal | llm_refusal
    item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    loop_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("care_loops.id", ondelete="CASCADE"), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="open")  # open | approved | rejected
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, default="")


class ModelRegistry(IdMixin, Base):
    __tablename__ = "model_registry"
    name: Mapped[str] = mapped_column(String(20))  # risk | uplift_t0 | uplift_t1
    version: Mapped[str] = mapped_column(String(40))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    calibration: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    fairness: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    artifact_path: Mapped[str] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SimRun(IdMixin, Base):
    __tablename__ = "sim_runs"
    policy: Mapped[str] = mapped_column(String(200))  # comma-separated policies in this run
    kind: Mapped[str] = mapped_column(String(12), default="compare")  # compare | sensitivity
    params: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    seed: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), default="queued")  # queued | running | done | error
    results: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(120), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FairnessSnapshot(IdMixin, Base):
    __tablename__ = "fairness_snapshots"
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    group_by: Mapped[str] = mapped_column(String(30))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class DemoState(Base):
    """Tracks the seed checksum so `make seed` can prove determinism."""

    __tablename__ = "demo_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seed: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64))
    counts: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    seeded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
