"""Tamper-evident audit chain (spec section 4.3).

    hash = sha256(prev_hash || canonical_json(payload) || created_at)

where `payload` covers every meaningful column of the event (loop, states, actor,
reason, payload). Two chains are kept: one per loop, and one global chain across all
events in insertion order (`seq`). Editing any stored row changes its recomputed hash, so
`verify_chain` reports the first broken event.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.clock import as_utc
from app.models import LoopEvent

GENESIS = "0" * 64


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _ts(dt: datetime) -> str:
    # Microsecond precision, UTC, no tz suffix: identical on Postgres and SQLite.
    return as_utc(dt).astimezone(UTC).replace(tzinfo=None).isoformat(timespec="microseconds")


def event_body(ev: LoopEvent) -> dict[str, Any]:
    return {
        "loop_id": str(ev.loop_id),
        "from_state": ev.from_state,
        "to_state": ev.to_state,
        "actor": ev.actor,
        "reason": ev.reason,
        "payload": ev.payload or {},
    }


def compute_hash(prev_hash: str, body: dict[str, Any], created_at: datetime) -> str:
    h = hashlib.sha256()
    h.update(prev_hash.encode())
    h.update(canonical_json(body).encode())
    h.update(_ts(created_at).encode())
    return h.hexdigest()


class ChainHead:
    """Caches chain heads during bulk seeding so we do not query per insert."""

    def __init__(self) -> None:
        self.loop_heads: dict[uuid.UUID, str] = {}
        self.global_head: str | None = None
        self.seq: int | None = None


def append_event(
    db: Session,
    loop_id: uuid.UUID,
    from_state: str | None,
    to_state: str,
    actor: str,
    reason: str,
    payload: dict[str, Any] | None,
    created_at: datetime,
    head: ChainHead | None = None,
) -> LoopEvent:
    if head is not None and head.seq is not None:
        seq = head.seq + 1
        global_prev = head.global_head or GENESIS
        loop_prev = head.loop_heads.get(loop_id, GENESIS)
    else:
        _lock_chain(db)
        last_global = db.scalar(select(LoopEvent).order_by(LoopEvent.seq.desc()).limit(1))
        seq = (last_global.seq + 1) if last_global else 1
        global_prev = last_global.global_hash if last_global else GENESIS
        last_loop = db.scalar(
            select(LoopEvent).where(LoopEvent.loop_id == loop_id).order_by(LoopEvent.seq.desc()).limit(1)
        )
        loop_prev = last_loop.hash if last_loop else GENESIS

    ev = LoopEvent(
        id=uuid.uuid4(),
        seq=seq,
        loop_id=loop_id,
        from_state=from_state,
        to_state=to_state,
        actor=actor,
        reason=reason,
        payload=payload or {},
        created_at=created_at,
        prev_hash=loop_prev,
        global_prev_hash=global_prev,
    )
    body = event_body(ev)
    ev.hash = compute_hash(loop_prev, body, created_at)
    ev.global_hash = compute_hash(global_prev, {**body, "seq": seq}, created_at)
    db.add(ev)
    if head is not None:
        head.seq = seq
        head.global_head = ev.global_hash
        head.loop_heads[loop_id] = ev.hash
    else:
        db.flush()  # the next append must see this row as the chain head
    return ev


def _lock_chain(db: Session) -> None:
    """Serialise appends to the global chain (transaction-scoped advisory lock), so two
    concurrent writers can never claim the same sequence number."""
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(724501)"))


def verify_chain(db: Session, loop_id: uuid.UUID | None = None) -> dict[str, Any]:
    """Recompute every hash. Returns {valid, broken_at, checked, chain}."""
    q = select(LoopEvent).order_by(LoopEvent.seq)
    if loop_id is not None:
        q = q.where(LoopEvent.loop_id == loop_id)
    loop_prev: dict[uuid.UUID, str] = {}
    global_prev = GENESIS
    checked = 0
    for ev in db.scalars(q).yield_per(2000):
        body = event_body(ev)
        expected_prev = loop_prev.get(ev.loop_id, GENESIS)
        if ev.prev_hash != expected_prev or ev.hash != compute_hash(expected_prev, body, ev.created_at):
            return {"valid": False, "broken_at": str(ev.id), "broken_seq": ev.seq, "checked": checked}
        if loop_id is None:
            if ev.global_prev_hash != global_prev or ev.global_hash != compute_hash(
                global_prev, {**body, "seq": ev.seq}, ev.created_at
            ):
                return {"valid": False, "broken_at": str(ev.id), "broken_seq": ev.seq, "checked": checked}
            global_prev = ev.global_hash
        loop_prev[ev.loop_id] = ev.hash
        checked += 1
    return {"valid": True, "broken_at": None, "broken_seq": None, "checked": checked}


def event_count(db: Session) -> int:
    return int(db.scalar(select(func.count(LoopEvent.id))) or 0)
