from fastapi import APIRouter, Depends, HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import error_payload
from app.core.security import ALGORITHM, create_access_token, create_refresh_token, verify_password
from app.db.session import get_db
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


@router.post("/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail=error_payload("invalid_credentials", "Invalid email or password"))
    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "token_type": "Bearer",
        "expires_in": settings.access_token_minutes * 60,
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "roles": ["admin"] if settings.is_admin_email(user.email) else ["operator"],
        },
    }


@router.post("/refresh")
def refresh(payload: RefreshIn):
    try:
        decoded = jwt.decode(payload.refresh_token, settings.secret_key, algorithms=[ALGORITHM])
        if decoded.get("type") != "refresh":
            raise HTTPException(status_code=401, detail=error_payload("refresh_invalid", "Invalid refresh token"))
        return {"access_token": create_access_token(decoded["sub"]), "token_type": "Bearer", "expires_in": settings.access_token_minutes * 60}
    except JWTError:
        raise HTTPException(status_code=401, detail=error_payload("refresh_invalid", "Invalid refresh token")) from None
