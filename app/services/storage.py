from pathlib import Path
from uuid import uuid4

from app.core.config import settings


def save_upload(request_id: str, filename: str, content: bytes) -> str:
    root = Path(settings.storage_root) / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    file_path = root / f"{request_id}_{uuid4().hex}_{filename}"
    file_path.write_bytes(content)
    return str(file_path).replace("\\", "/")


def export_path(export_id: str, fmt: str) -> str:
    root = Path(settings.storage_root) / "exports"
    root.mkdir(parents=True, exist_ok=True)
    return str((root / f"{export_id}.{fmt}")).replace("\\", "/")
