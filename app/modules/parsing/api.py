from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import error_payload
from app.db.session import get_db
from app.jobs.queue import queue
from app.jobs.tasks import parsing_task
from app.models import RequestItem, User

router = APIRouter(prefix="/requests/{request_id}/parsing", tags=["parsing"])


class ParseStart(BaseModel):
    force_reparse: bool = False


@router.post("/start")
def start_parsing(request_id: str, payload: ParseStart, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    req = db.get(RequestItem, request_id)
    if not req:
        raise HTTPException(status_code=404, detail=error_payload("request_not_found", "Request not found"))
    if req.parse_status == "running":
        raise HTTPException(status_code=400, detail=error_payload("parsing_already_running", "Parsing already running"))
    req.parse_status = "queued"
    db.commit()
    try:
        job = queue.enqueue(parsing_task, request_id)
        return {"request_id": request_id, "job_id": job.id, "status": "queued"}
    except Exception:
        parsing_task(request_id)
        return {"request_id": request_id, "job_id": None, "status": "completed_sync"}


@router.get("/status")
def parsing_status(request_id: str, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    req = db.get(RequestItem, request_id)
    if not req:
        raise HTTPException(status_code=404, detail=error_payload("request_not_found", "Request not found"))
    progress = 100 if req.parse_status == "completed" else 0 if req.parse_status == "not_started" else 50
    return {
        "request_id": request_id,
        "status": req.parse_status,
        "progress": progress,
        "parsed_items": req.total_items,
        "started_at": req.updated_at.isoformat(),
        "finished_at": req.updated_at.isoformat() if req.parse_status == "completed" else None,
        "error": None,
    }
