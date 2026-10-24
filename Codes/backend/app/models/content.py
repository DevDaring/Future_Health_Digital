"""Clinician-approved content, translations, conversations and the QA trail."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, JSONType
from app.models.base import IdMixin, TimestampMixin


class ContentTemplate(IdMixin, TimestampMixin, Base):
    __tablename__ = "content_templates"
    program: Mapped[str] = mapped_column(String(20))  # DIABETES | COLORECTAL | BREAST | ANY
    severity: Mapped[str] = mapped_column(String(10))  # routine | high | urgent | any
    key: Mapped[str] = mapped_column(String(40), index=True)
    language: Mapped[str] = mapped_column(String(5), default="en")
    body: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(10), default="draft")  # draft | approved | retired


class ApprovedTranslation(IdMixin, TimestampMixin, Base):
    __tablename__ = "approved_translations"
    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("content_templates.id", ondelete="CASCADE"), index=True
    )
    language: Mapped[str] = mapped_column(String(5))
    body: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[str] = mapped_column(String(120))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    note: Mapped[str] = mapped_column(String(120), default="demo fixture — not clinically validated")


class Conversation(IdMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    loop_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("care_loops.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(12), default="whatsapp")
    language: Mapped[str] = mapped_column(String(5))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    magic_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    step: Mapped[str] = mapped_column(String(20), default="start")
    context: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class Message(IdMixin, Base):
    __tablename__ = "messages"
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    sender: Mapped[str] = mapped_column(String(14))  # patient | navigator_ai | human | system
    text: Mapped[str] = mapped_column(Text)
    text_en: Mapped[str] = mapped_column(Text, default="")
    template_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("content_templates.id"), nullable=True)
    translation_check_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("translation_checks.id"), nullable=True
    )
    red_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    kind: Mapped[str] = mapped_column(String(20), default="text")  # text | slots | emergency | quick
    meta: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TranslationCheck(IdMixin, Base):
    __tablename__ = "translation_checks"
    loop_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("care_loops.id", ondelete="CASCADE"), nullable=True)
    template_key: Mapped[str] = mapped_column(String(40), default="")
    language: Mapped[str] = mapped_column(String(5))
    source_en: Mapped[str] = mapped_column(Text)
    simplified_en: Mapped[str] = mapped_column(Text, default="")
    translated: Mapped[str] = mapped_column(Text)
    back_translated: Mapped[str] = mapped_column(Text)
    judge_score: Mapped[float] = mapped_column(Float)
    entity_match: Mapped[bool] = mapped_column(Boolean)
    discrepancies: Mapped[list[str]] = mapped_column(JSONType, default=list)
    passed: Mapped[bool] = mapped_column(Boolean)
    fell_back: Mapped[bool] = mapped_column(Boolean, default=False)
    final_text: Mapped[str] = mapped_column(Text, default="")
    provider: Mapped[str] = mapped_column(String(60), default="mock")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TeachBackAttempt(IdMixin, Base):
    __tablename__ = "teach_back_attempts"
    loop_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("care_loops.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text)
    patient_answer: Mapped[str] = mapped_column(Text)
    answer_en: Mapped[str] = mapped_column(Text)
    rubric: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    passed: Mapped[bool] = mapped_column(Boolean)
    feedback: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LLMCache(Base):
    """Cache of deterministic pipeline outputs (same template + language + literacy gives
    the same checked message). Keeps patient chat fast with a real LLM."""

    __tablename__ = "llm_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
