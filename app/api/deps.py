from jose import JWTError, jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import error_payload
from app.core.security import ALGORITHM
from app.db.session import get_db
from app.models import User

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail=error_payload("unauthorized", "Invalid token type"))
        user = db.get(User, payload.get("sub"))
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail=error_payload("unauthorized", "User inactive"))
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail=error_payload("unauthorized", "Invalid token")) from None


def require_admin(current: User = Depends(get_current_user)) -> User:
    if current.email != "admin@local":
        raise HTTPException(status_code=401, detail=error_payload("unauthorized", "Admin role required"))
    return current
