"""Care-loop state machine (spec section 4.2).

    RESULT_RECEIVED → NOTIFIED → ENGAGED → UNDERSTOOD → BOOKED → ATTENDED → CLOSED
    side exits: UNREACHABLE, DECLINED (informed refusal), NO_SHOW (→ ENGAGED again)
    any open state → ESCALATED → (human) back to the previous state
    SLA expiry sets the `breached` flag and moves the loop to BREACHED, which stays actionable.

Design note: the navigator runs teach-back *before* confirming the booking, so a loop
moves ENGAGED → UNDERSTOOD → BOOKED in order. If teach-back fails twice we never block
care: ENGAGED → BOOKED is allowed and a human navigator is asked to follow up.
"""

from __future__ import annotations

STATES = (
    "RESULT_RECEIVED",
    "NOTIFIED",
    "ENGAGED",
    "UNDERSTOOD",
    "BOOKED",
    "ATTENDED",
    "CLOSED",
    "UNREACHABLE",
    "DECLINED",
    "NO_SHOW",
    "ESCALATED",
    "BREACHED",
)

# The forward funnel used by dashboards.
FUNNEL = ("RESULT_RECEIVED", "NOTIFIED", "ENGAGED", "UNDERSTOOD", "BOOKED", "ATTENDED", "CLOSED")

TERMINAL = {"CLOSED", "DECLINED"}
OPEN_STATES = set(STATES) - TERMINAL - {"ATTENDED"}

ALLOWED: dict[str, set[str]] = {
    "RESULT_RECEIVED": {"NOTIFIED", "UNREACHABLE", "BOOKED"},
    "NOTIFIED": {"ENGAGED", "UNREACHABLE", "DECLINED", "BOOKED"},
    "ENGAGED": {"UNDERSTOOD", "BOOKED", "DECLINED", "UNREACHABLE"},
    "UNDERSTOOD": {"BOOKED", "DECLINED"},
    "BOOKED": {"ATTENDED", "NO_SHOW", "DECLINED"},
    "ATTENDED": {"CLOSED"},
    "NO_SHOW": {"ENGAGED", "BOOKED", "UNREACHABLE", "DECLINED"},
    "UNREACHABLE": {"NOTIFIED", "ENGAGED"},
    "BREACHED": {"NOTIFIED", "ENGAGED", "UNDERSTOOD", "BOOKED", "ATTENDED", "UNREACHABLE", "DECLINED"},
    "CLOSED": set(),
    "DECLINED": set(),
    "ESCALATED": set(),  # handled specially: returns to `escalated_from`
}


class InvalidTransition(Exception):
    def __init__(self, from_state: str, to_state: str) -> None:
        super().__init__(f"Invalid transition {from_state} → {to_state}")
        self.from_state = from_state
        self.to_state = to_state


def can_transition(from_state: str, to_state: str, escalated_from: str | None = None) -> bool:
    if to_state not in STATES:
        return False
    if to_state == "ESCALATED":
        return from_state not in TERMINAL and from_state != "ESCALATED"
    if to_state == "BREACHED":
        return from_state in {"RESULT_RECEIVED", "NOTIFIED", "ENGAGED", "UNDERSTOOD", "NO_SHOW", "UNREACHABLE"}
    if from_state == "ESCALATED":
        # A human resolves the escalation and returns the loop to where it was,
        # or records a refusal / attendance directly.
        return to_state == escalated_from or to_state in {"DECLINED", "ATTENDED", "BOOKED"}
    return to_state in ALLOWED.get(from_state, set())


def validate(from_state: str, to_state: str, escalated_from: str | None = None) -> None:
    if not can_transition(from_state, to_state, escalated_from):
        raise InvalidTransition(from_state, to_state)


def funnel_rank(state: str, escalated_from: str | None = None) -> int:
    """How far along the forward funnel a loop got (for funnel counting)."""
    effective = escalated_from if state == "ESCALATED" and escalated_from else state
    mapping = {s: i for i, s in enumerate(FUNNEL)}
    if effective in mapping:
        return mapping[effective]
    if effective == "NO_SHOW":
        return mapping["BOOKED"]
    if effective in {"UNREACHABLE", "BREACHED"}:
        return mapping["RESULT_RECEIVED"]
    if effective == "DECLINED":
        return mapping["ENGAGED"]
    return 0
