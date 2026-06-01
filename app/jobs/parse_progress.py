from datetime import datetime, timezone

from app.jobs.queue import redis_conn

_TTL_SEC = 900


def _phase_key(request_id: str) -> str:
    return f"parse:progress:{request_id}"


def _ocr_since_key(request_id: str) -> str:
    return f"parse:ocr_since:{request_id}"


def set_parse_phase(request_id: str, phase: str | None) -> None:
    if not phase:
        redis_conn.delete(_phase_key(request_id), _ocr_since_key(request_id))
        return
    redis_conn.setex(_phase_key(request_id), _TTL_SEC, phase)
    if phase == "ocr":
        redis_conn.setex(_ocr_since_key(request_id), _TTL_SEC, datetime.now(timezone.utc).isoformat())


def get_parse_progress(request_id: str) -> dict:
    raw = redis_conn.get(_phase_key(request_id))
    phase = raw.decode("utf-8") if raw else None
    since_raw = redis_conn.get(_ocr_since_key(request_id))
    ocr_started_at = since_raw.decode("utf-8") if since_raw else None
    ocr_elapsed_sec = None
    if ocr_started_at:
        try:
            started = datetime.fromisoformat(ocr_started_at.replace("Z", "+00:00"))
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            ocr_elapsed_sec = max(0, int((datetime.now(timezone.utc) - started).total_seconds()))
        except ValueError:
            ocr_elapsed_sec = None
    return {
        "phase": phase,
        "ocr_active": phase == "ocr",
        "ocr_started_at": ocr_started_at,
        "ocr_elapsed_sec": ocr_elapsed_sec,
    }
