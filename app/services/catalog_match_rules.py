import json
import re
from pathlib import Path
from uuid import uuid4

from app.core.config import settings


DEFAULT_CATALOG_MATCH_RULES = [
    {
        "id": "meter_with_connectors_requires_kmch",
        "description": "Если в КП есть счетчик с присоединителями, искать позиции с КМЧ.",
        "when_all": [r"\bсчетчик", r"\bприсоединител"],
        "require_any": [r"\bкмч\b"],
    }
]


def _rules_path() -> Path:
    root = Path(settings.storage_root)
    root.mkdir(parents=True, exist_ok=True)
    return root / "catalog_match_rules.json"


def _sanitize_rule(rule: dict) -> dict:
    when_all = [str(x).strip() for x in (rule.get("when_all") or []) if str(x).strip()]
    require_any = [str(x).strip() for x in (rule.get("require_any") or []) if str(x).strip()]
    return {
        "id": str(rule.get("id") or uuid4()),
        "description": str(rule.get("description") or "").strip(),
        "when_all": when_all,
        "require_any": require_any,
    }


def list_catalog_match_rules() -> list[dict]:
    path = _rules_path()
    if not path.exists():
        return [_sanitize_rule(x) for x in DEFAULT_CATALOG_MATCH_RULES]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return [_sanitize_rule(x) for x in DEFAULT_CATALOG_MATCH_RULES]
        rules = [_sanitize_rule(x) for x in payload if isinstance(x, dict)]
        return [r for r in rules if r["when_all"] and r["require_any"]]
    except Exception:
        return [_sanitize_rule(x) for x in DEFAULT_CATALOG_MATCH_RULES]


def save_catalog_match_rules(rules: list[dict]) -> list[dict]:
    sanitized = [_sanitize_rule(x) for x in rules if isinstance(x, dict)]
    sanitized = [r for r in sanitized if r["when_all"] and r["require_any"]]
    _rules_path().write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding="utf-8")
    return sanitized


def add_catalog_match_rule(description: str, when_all: list[str], require_any: list[str]) -> dict:
    rules = list_catalog_match_rules()
    rule = _sanitize_rule(
        {
            "id": str(uuid4()),
            "description": description,
            "when_all": when_all,
            "require_any": require_any,
        }
    )
    if not rule["when_all"] or not rule["require_any"]:
        raise ValueError("Rule must contain non-empty when_all and require_any")
    rules.append(rule)
    save_catalog_match_rules(rules)
    return rule


def delete_catalog_match_rule(rule_id: str) -> bool:
    if not rule_id:
        return False
    rules = list_catalog_match_rules()
    filtered = [x for x in rules if x.get("id") != rule_id]
    if len(filtered) == len(rules):
        return False
    save_catalog_match_rules(filtered)
    return True


def update_catalog_match_rule(rule_id: str, description: str, when_all: list[str], require_any: list[str]) -> dict | None:
    if not rule_id:
        return None
    rules = list_catalog_match_rules()
    updated: dict | None = None
    for idx, item in enumerate(rules):
        if item.get("id") != rule_id:
            continue
        next_item = _sanitize_rule(
            {
                "id": rule_id,
                "description": description,
                "when_all": when_all,
                "require_any": require_any,
            }
        )
        if not next_item["when_all"] or not next_item["require_any"]:
            raise ValueError("Rule must contain non-empty when_all and require_any")
        rules[idx] = next_item
        updated = next_item
        break
    if updated is None:
        return None
    save_catalog_match_rules(rules)
    return updated


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    text = value.lower().replace("ё", "е")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def apply_catalog_rule_filter(item_name: str | None, product_name: str | None, rules: list[dict] | None = None) -> tuple[bool, list[str]]:
    item = _normalize(item_name)
    product = _normalize(product_name)
    if not item:
        return True, []
    reasons: list[str] = []
    active_rules = rules if rules is not None else list_catalog_match_rules()
    for rule in active_rules:
        when_all = rule.get("when_all", [])
        require_any = rule.get("require_any", [])
        if when_all and not all(re.search(pattern, item) for pattern in when_all):
            continue
        if require_any and not any(re.search(pattern, product) for pattern in require_any):
            reasons.append(f"rule_block:{rule.get('id')}")
            return False, reasons
        reasons.append(f"rule_pass:{rule.get('id')}")
    return True, reasons
