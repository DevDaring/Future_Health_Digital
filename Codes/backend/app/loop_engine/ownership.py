"""Case ownership: every care loop has exactly one named owner from the moment the result
arrives until the loop is closed.

Default rule (configurable per programme in a pilot):
* urgent results go to a clinician, so a doctor owns them from the start;
* otherwise a navigator who speaks the patient's language owns the case;
* otherwise the care coordinator does.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CareLoop, User

STAFF_ROLES = ("clinician", "navigator", "coordinator")


def _staff(db: Session) -> dict[str, list[User]]:
    out: dict[str, list[User]] = {r: [] for r in STAFF_ROLES}
    for u in db.scalars(select(User).where(User.role.in_(STAFF_ROLES)).order_by(User.email)):
        out[u.role].append(u)
    return out


def pick_owner(staff: dict[str, list[User]], severity: str, language: str, use_navigators: bool = True) -> User | None:
    if severity == "urgent" and staff["clinician"]:
        return staff["clinician"][0]
    for nav in staff["navigator"] if use_navigators else []:
        if language in (nav.languages or []):
            return nav
    if staff["coordinator"]:
        return staff["coordinator"][0]
    return next((u for role in STAFF_ROLES for u in staff[role]), None)


def assign_default_owner(db: Session, loop: CareLoop, staff: dict[str, list[User]] | None = None,
                         use_navigators: bool = True) -> User | None:
    if loop.assigned_to is not None:
        return None
    owner = pick_owner(staff or _staff(db), loop.screening.severity, loop.patient.preferred_language, use_navigators)
    if owner is not None:
        loop.assigned_to = owner.id
    return owner


def assign_all_unowned(db: Session, use_navigators: bool = True) -> int:
    """Backfill owners. The seeded backlog passes use_navigators=False so the demo navigator
    keeps a realistic caseload; the coordinator owns the rest."""
    staff = _staff(db)
    n = 0
    for loop in db.scalars(select(CareLoop).where(CareLoop.assigned_to.is_(None))).unique():
        if assign_default_owner(db, loop, staff, use_navigators) is not None:
            n += 1
    db.flush()
    return n


def clinician_on_duty(db: Session) -> User | None:
    return db.scalar(select(User).where(User.role == "clinician").order_by(User.email).limit(1))
