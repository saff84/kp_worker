from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import error_payload
from app.db.session import get_db
from app.models import RequestItem, User
from app.shared.pagination import paginate

router = APIRouter(prefix="/requests", tags=["requests"])


class RequestCreate(BaseModel):
    source_type: str = "text"
    input_text: str | None = None
    title: str | None = None


@router.post("")
def create_request(payload: RequestCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    req = RequestItem(created_by=current.id, source_type=payload.source_type, input_text=payload.input_text, title=payload.title)
    db.add(req)
    db.commit()
    db.refresh(req)
    return {"id": req.id, "status": req.status, "source_type": req.source_type, "title": req.title, "created_at": req.created_at.isoformat()}


@router.get("")
def list_requests(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    q = select(RequestItem)
    if current.email != "admin@local":
        q = q.where(RequestItem.created_by == current.id)
    if status:
        q = q.where(RequestItem.status == status)
    rows = []
    for req in db.scalars(q.order_by(RequestItem.created_at.desc())).all():
        rows.append(
            {
                "id": req.id,
                "status": req.status,
                "title": req.title,
                "created_at": req.created_at.isoformat(),
                "updated_at": req.updated_at.isoformat(),
                "total_items": req.total_items,
                "matched_items": req.matched_items,
                "needs_review_items": req.needs_review_items,
            }
        )
    return paginate(rows, page, page_size)


@router.get("/{request_id}")
def get_request(request_id: str, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    req = db.get(RequestItem, request_id)
    if not req:
        raise HTTPException(status_code=404, detail=error_payload("request_not_found", "Request not found"))
    if current.email != "admin@local" and req.created_by != current.id:
        raise HTTPException(status_code=401, detail=error_payload("access_denied", "No access"))
    return {
        "id": req.id,
        "status": req.status,
        "source_type": req.source_type,
        "title": req.title,
        "created_by": req.created_by,
        "created_at": req.created_at.isoformat(),
        "updated_at": req.updated_at.isoformat(),
        "counters": {
            "total_items": req.total_items,
            "matched_items": req.matched_items,
            "needs_review_items": req.needs_review_items,
        },
    }
