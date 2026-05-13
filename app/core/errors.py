from uuid import uuid4


def error_payload(code: str, message: str, details: list[dict] | None = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
            "request_id": f"req-{uuid4().hex[:10]}",
        }
    }
