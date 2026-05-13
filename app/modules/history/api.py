from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import AuditLog, User
from app.shared.pagination import paginate

router = APIRouter(prefix="/history", tags=["history"])


@router.get("")
def list_history(page: int = 1, page_size: int = 20, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    logs = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc())).all()
    rows = [
        {
            "id": l.id,
            "actor_user_id": l.actor_user_id,
            "action": l.action,
            "entity_type": l.entity_type,
            "entity_id": l.entity_id,
            "request_id": l.request_id,
            "created_at": l.created_at.isoformat(),
        }
        for l in logs
    ]
    return paginate(rows, page, page_size)
