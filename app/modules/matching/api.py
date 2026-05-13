from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import error_payload
from app.db.session import get_db
from app.jobs.queue import queue
from app.jobs.tasks import matching_task
from app.models import RequestItem, User

router = APIRouter(prefix="/requests/{request_id}/matching", tags=["matching"])


class MatchStart(BaseModel):
    strategy: str = "default"
    auto_approve_threshold: float = Field(default=0.72, ge=0, le=1)


@router.post("/start")
def start_matching(request_id: str, payload: MatchStart, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    req = db.get(RequestItem, request_id)
    if not req:
        raise HTTPException(status_code=404, detail=error_payload("request_not_found", "Request not found"))
    if req.parse_status != "completed":
        raise HTTPException(status_code=400, detail=error_payload("parsing_not_completed", "Parsing must be completed first"))
    if req.match_status == "running":
        raise HTTPException(status_code=400, detail=error_payload("matching_already_running", "Matching already running"))
    req.match_status = "queued"
    db.commit()
    try:
        job = queue.enqueue(matching_task, request_id, payload.auto_approve_threshold)
        return {"request_id": request_id, "job_id": job.id, "status": "queued"}
    except Exception:
        matching_task(request_id, payload.auto_approve_threshold)
        return {"request_id": request_id, "job_id": None, "status": "completed_sync"}


@router.get("/status")
def matching_status(request_id: str, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    req = db.get(RequestItem, request_id)
    if not req:
        raise HTTPException(status_code=404, detail=error_payload("request_not_found", "Request not found"))
    progress = 100 if req.match_status == "completed" else 0 if req.match_status == "not_started" else 50
    return {
        "request_id": request_id,
        "status": req.match_status,
        "progress": progress,
        "total_items": req.total_items,
        "auto_matched": req.matched_items,
        "needs_review": req.needs_review_items,
        "started_at": req.updated_at.isoformat(),
        "finished_at": req.updated_at.isoformat() if req.match_status == "completed" else None,
        "error": None,
    }
