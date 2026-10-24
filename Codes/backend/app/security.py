"""JWT auth, password hashing and role-based access control.

The RBAC matrix (spec section 11) is encoded once in `CAPABILITIES` and enforced with
the `require(capability)` dependency, so the API and its tests share one source of truth.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)

ROLES = ("admin", "coordinator", "clinician", "navigator")

CAPABILITIES: dict[str, set[str]] = {
    "worklist": {"admin", "coordinator", "clinician", "navigator"},
    "pii_full": {"admin"},
    "patient_twin": {"admin", "coordinator", "clinician"},
    "approve_templates": {"admin", "clinician"},
    "run_twin": {"admin", "coordinator", "clinician"},
    "governance_read": {"admin", "coordinator", "clinician"},
    "governance_write": {"admin"},
    "loop_write": {"admin", "coordinator", "clinician", "navigator"},
    "demo_admin": {"admin"},
}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(password, hashed)
    except ValueError:
        return False


def create_token(user: User) -> str:
    s = get_settings()
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": datetime.now(UTC) + timedelta(minutes=s.jwt_expiry_minutes),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        data = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc
    user = db.scalar(select(User).where(User.id == _uuid(data.get("sub"))))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return user


def _uuid(value: object) -> object:
    import uuid

    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def can(user: User, capability: str) -> bool:
    return user.role in CAPABILITIES[capability]


def require(capability: str):  # noqa: ANN201 - returns a FastAPI dependency
    def _dep(user: Annotated[User, Depends(current_user)]) -> User:
        if not can(user, capability):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Role '{user.role}' lacks '{capability}'")
        return user

    return _dep


CurrentUser = Annotated[User, Depends(current_user)]
