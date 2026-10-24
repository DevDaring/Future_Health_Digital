"""Login with e-mail or username (the jury account uses a username)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.schemas import LoginIn, LoginOut, UserOut
from app.security import CurrentUser, create_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def user_out(u: User) -> UserOut:
    return UserOut(id=str(u.id), email=u.email, username=u.username, role=u.role, display_name=u.display_name, languages=u.languages or [])


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, db: Annotated[Session, Depends(get_db)]) -> LoginOut:
    ident = body.username.strip()
    user = db.scalar(select(User).where(or_(func.lower(User.email) == ident.lower(), User.username == ident)))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong username or password")
    return LoginOut(access_token=create_token(user), user=user_out(user))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return user_out(user)
