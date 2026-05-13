import hashlib
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.core.config import settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    salt = b"parser-kp-prod-salt"
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 180000)
    return digest.hex()


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


def create_token(sub: str, token_type: str, expires: timedelta) -> str:
    payload = {"sub": sub, "type": token_type, "exp": datetime.now(timezone.utc) + expires}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_access_token(sub: str) -> str:
    return create_token(sub, "access", timedelta(minutes=settings.access_token_minutes))


def create_refresh_token(sub: str) -> str:
    return create_token(sub, "refresh", timedelta(days=settings.refresh_token_days))
