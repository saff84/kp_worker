import json
from pathlib import Path

from app.core.config import settings


def _calibration_path() -> Path:
    root = Path(settings.storage_root)
    root.mkdir(parents=True, exist_ok=True)
    return root / "ocr_calibration.json"


def _ratio_pair(value: str, default: tuple[float, float]) -> list[float]:
    try:
        left_raw, right_raw = [x.strip() for x in str(value).split(",", 1)]
        left = float(left_raw)
        right = float(right_raw)
    except Exception:
        return [default[0], default[1]]
    left = max(0.0, min(1.0, left))
    right = max(0.0, min(1.0, right))
    if right <= left:
        return [default[0], default[1]]
    return [left, right]


def default_ocr_calibration() -> dict:
    name = _ratio_pair(settings.ocr_name_col_range, (0.06, 0.47))
    qty = _ratio_pair(settings.ocr_qty_col_range, (0.72, 0.84))
    y = _ratio_pair(settings.ocr_table_y_range, (0.08, 0.94))
    return {
        "name_col": name,
        "qty_col": qty,
        "table_y": y,
    }


def load_ocr_calibration() -> dict:
    defaults = default_ocr_calibration()
    path = _calibration_path()
    if not path.exists():
        return defaults
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return defaults
    if not isinstance(payload, dict):
        return defaults
    return {
        "name_col": _ratio_pair(payload.get("name_col", ""), tuple(defaults["name_col"])),
        "qty_col": _ratio_pair(payload.get("qty_col", ""), tuple(defaults["qty_col"])),
        "table_y": _ratio_pair(payload.get("table_y", ""), tuple(defaults["table_y"])),
    }


def save_ocr_calibration(payload: dict) -> dict:
    defaults = default_ocr_calibration()
    normalized = {
        "name_col": _ratio_pair(payload.get("name_col", ""), tuple(defaults["name_col"])),
        "qty_col": _ratio_pair(payload.get("qty_col", ""), tuple(defaults["qty_col"])),
        "table_y": _ratio_pair(payload.get("table_y", ""), tuple(defaults["table_y"])),
    }
    _calibration_path().write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized
