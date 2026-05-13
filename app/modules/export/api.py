from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import error_payload
from app.db.session import get_db
from app.jobs.queue import queue
from app.jobs.tasks import export_task
from app.models import ExportFile, RequestItem, User

router = APIRouter(prefix="/requests/{request_id}/export", tags=["export"])


class ExportIn(BaseModel):
    format: str = "xlsx"
    include_unmatched: bool = True


@router.post("")
def start_export(request_id: str, payload: ExportIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    req = db.get(RequestItem, request_id)
    if not req:
        raise HTTPException(status_code=404, detail=error_payload("request_not_found", "Request not found"))
    export_format = (payload.format or "xlsx").lower().strip()
    if export_format not in {"csv", "xls", "xlsx"}:
        raise HTTPException(status_code=400, detail=error_payload("invalid_export_format", "Supported formats: csv, xls, xlsx"))
    # Keep backward compatibility: treat legacy "xls" request as xlsx workbook.
    if export_format == "xls":
        export_format = "xlsx"
    exp = ExportFile(request_id=request_id, format=export_format, storage_key=f"pending/{uuid4().hex}", status="queued")
    db.add(exp)
    db.commit()
    db.refresh(exp)
    try:
        job = queue.enqueue(export_task, request_id, exp.id, payload.include_unmatched)
        return {"request_id": request_id, "export_id": exp.id, "status": "queued", "job_id": job.id}
    except Exception:
        export_task(request_id, exp.id, payload.include_unmatched)
        return {"request_id": request_id, "export_id": exp.id, "status": "completed_sync", "job_id": None}


@router.get("/{export_id}")
def export_status(request_id: str, export_id: str, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    exp = db.get(ExportFile, export_id)
    if not exp or exp.request_id != request_id:
        raise HTTPException(status_code=404, detail=error_payload("export_not_found", "Export not found"))
    return {
        "export_id": exp.id,
        "status": exp.status,
        "format": exp.format,
        "download_url": f"/api/v1/requests/{request_id}/export/{export_id}/download" if exp.status == "completed" else None,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat() if exp.status == "completed" else None,
    }


@router.get("/{export_id}/download")
def download_export(request_id: str, export_id: str, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    exp = db.get(ExportFile, export_id)
    if not exp or exp.request_id != request_id:
        raise HTTPException(status_code=404, detail=error_payload("export_not_found", "Export not found"))
    if exp.status != "completed":
        raise HTTPException(status_code=409, detail=error_payload("export_not_ready", "Export is not ready yet"))
    file_path = Path(exp.storage_key)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=error_payload("export_file_not_found", "Export file not found"))
    filename = f"export_{request_id}.{exp.format}"
    media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if exp.format == "xlsx" else "text/csv"
    return FileResponse(path=str(file_path), filename=filename, media_type=media_type)
