from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import error_payload
from app.db.session import get_db
from app.jobs.parse_progress import clear_parse_cancel, get_parse_progress, request_parse_cancel
from app.jobs.queue import PARSE_JOB_TIMEOUT_SEC, queue
from app.jobs.tasks import parsing_task
from app.models import RequestItem, User


def _is_stale_running(updated_at: datetime, *, minutes: int = 6) -> bool:
    ts = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - ts > timedelta(minutes=minutes)

router = APIRouter(prefix="/requests/{request_id}/parsing", tags=["parsing"])


class ParseStart(BaseModel):
    force_reparse: bool = False


@router.post("/start")
def start_parsing(request_id: str, payload: ParseStart, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    req = db.get(RequestItem, request_id)
    if not req:
        raise HTTPException(status_code=404, detail=error_payload("request_not_found", "Request not found"))
    if req.parse_status == "running" and not (payload.force_reparse or _is_stale_running(req.updated_at)):
        raise HTTPException(status_code=400, detail=error_payload("parsing_already_running", "Parsing already running"))
    clear_parse_cancel(request_id)
    req.parse_status = "queued"
    req.updated_at = datetime.now(timezone.utc)
    db.commit()
    try:
        job = queue.enqueue(parsing_task, request_id, job_timeout=PARSE_JOB_TIMEOUT_SEC)
        return {"request_id": request_id, "job_id": job.id, "status": "queued"}
    except Exception:
        parsing_task(request_id)
        return {"request_id": request_id, "job_id": None, "status": "completed_sync"}


@router.post("/cancel")
def cancel_parsing(request_id: str, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    req = db.get(RequestItem, request_id)
    if not req:
        raise HTTPException(status_code=404, detail=error_payload("request_not_found", "Request not found"))
    request_parse_cancel(request_id)
    if req.parse_status in {"queued", "running"}:
        req.parse_status = "cancelled"
        req.status = "uploaded"
        req.updated_at = datetime.now(timezone.utc)
        db.commit()
    return {"request_id": request_id, "status": req.parse_status, "cancel_requested": True}


@router.get("/status")
def parsing_status(request_id: str, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    req = db.get(RequestItem, request_id)
    if not req:
        raise HTTPException(status_code=404, detail=error_payload("request_not_found", "Request not found"))
    progress = 100 if req.parse_status == "completed" else 0 if req.parse_status == "not_started" else 50
    ocr_info = get_parse_progress(request_id) if req.parse_status in {"queued", "running"} else {}
    error = None
    if req.parse_status == "failed":
        error = (
            "Не удалось извлечь позиции из файла. "
            "Часто это скан PDF без текстового слоя — нужен Tesseract в контейнере worker. "
            "Попробуйте XLSX/CSV или вставьте позиции текстом."
        )
    elif req.parse_status == "cancelled":
        error = "Парсинг отменен пользователем."
    return {
        "request_id": request_id,
        "status": req.parse_status,
        "progress": progress,
        "parsed_items": req.total_items,
        "started_at": req.updated_at.isoformat(),
        "finished_at": req.updated_at.isoformat() if req.parse_status in {"completed", "failed", "cancelled"} else None,
        "error": error,
        "phase": ocr_info.get("phase"),
        "ocr_active": bool(ocr_info.get("ocr_active")),
        "ocr_started_at": ocr_info.get("ocr_started_at"),
        "ocr_elapsed_sec": ocr_info.get("ocr_elapsed_sec"),
    }
