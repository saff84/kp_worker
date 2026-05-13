from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import error_payload
from app.db.session import get_db
from app.models import RequestItem, UploadedFile, User
from app.services.storage import save_upload

router = APIRouter(prefix="/requests/{request_id}/files", tags=["files"])


@router.post("")
def upload_file(request_id: str, file: UploadFile = File(...), db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    req = db.get(RequestItem, request_id)
    if not req:
        raise HTTPException(status_code=404, detail=error_payload("request_not_found", "Request not found"))
    content = file.file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail=error_payload("file_too_large", "File exceeds 20MB"))
    ext = Path(file.filename).suffix.lower()
    if ext not in {".xlsx", ".xls", ".csv", ".pdf", ".docx", ".txt"}:
        raise HTTPException(status_code=400, detail=error_payload("unsupported_file_type", "Unsupported file type"))
    key = save_upload(request_id, file.filename, content)
    saved = UploadedFile(
        request_id=request_id,
        original_filename=file.filename,
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        storage_key=key,
    )
    req.status = "uploaded"
    req.updated_at = datetime.now(timezone.utc)
    db.add(saved)
    db.commit()
    db.refresh(saved)
    return {
        "file_id": saved.id,
        "request_id": saved.request_id,
        "original_filename": saved.original_filename,
        "mime_type": saved.mime_type,
        "size_bytes": saved.size_bytes,
        "checksum_sha256": "demo",
        "uploaded_at": saved.created_at.isoformat(),
    }
