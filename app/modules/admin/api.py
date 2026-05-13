import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from openpyxl import Workbook

from app.api.deps import require_admin
from app.core.config import settings
from app.core.errors import error_payload
from app.db.session import get_db
from app.models import AnalogMapping, CompetitorMapping, ImportReport, MatchingRule, ProductCatalog, ProductCategory, User
from app.services.catalog_match_rules import (
    add_catalog_match_rule,
    delete_catalog_match_rule,
    list_catalog_match_rules,
    update_catalog_match_rule,
)
from app.services.hybrid_search import delete_catalog_products, reindex_catalog, upsert_catalog_products
from app.services.stop_words import load_stop_words, save_stop_words
from app.services.tabular_import import parse_table_bytes, to_bool, to_float
from app.shared.pagination import paginate

router = APIRouter(prefix="/admin", tags=["admin"])


class ProductIn(BaseModel):
    sku: str
    brand: str
    name: str
    category_id: str | None = None
    attributes: dict = Field(default_factory=dict)
    is_active: bool = True


class AnalogIn(BaseModel):
    product_id: str
    analog_product_id: str
    source: str = "manual"
    confidence: float = Field(default=1.0, ge=0, le=1)
    is_active: bool = True


class RuleIn(BaseModel):
    name: str
    priority: int = 100
    is_active: bool = True
    conditions: dict = Field(default_factory=dict)
    actions: dict = Field(default_factory=dict)


class CompetitorMappingIn(BaseModel):
    our_product_id: str
    competitor_brand: str
    competitor_name: str
    competitor_sku: str | None = None
    match_type: str = "analog"
    confidence: float = Field(default=0.8, ge=0, le=1)
    source: str = "manual"
    is_active: bool = True


class StopWordsIn(BaseModel):
    words: list[str] = Field(default_factory=list)


class CatalogMatchRuleIn(BaseModel):
    annotation: str = ""
    when_all: list[str] = Field(default_factory=list)
    require_any: list[str] = Field(default_factory=list)


def _store_import_report(
    db: Session,
    report_type: str,
    filename: str,
    actor_id: str | None,
    total_rows: int,
    created: int,
    updated: int,
    skipped: int,
    errors: list[dict],
) -> ImportReport:
    report = ImportReport(
        report_type=report_type,
        filename=filename,
        created_by=actor_id,
        total_rows=total_rows,
        created_count=created,
        updated_count=updated,
        skipped_count=skipped,
        errors=errors[:1000],
    )
    db.add(report)
    db.flush()
    return report


def _as_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _sync_catalog_vectors(db: Session, upsert_ids: set[str] | None = None, delete_ids: set[str] | None = None) -> dict:
    upserted = 0
    deleted = 0
    errors: list[str] = []
    if upsert_ids:
        products = db.scalars(select(ProductCatalog).where(ProductCatalog.id.in_(upsert_ids))).all()
        active_products = [p for p in products if p.is_active]
        if active_products:
            try:
                upserted = upsert_catalog_products(active_products)
            except Exception as exc:
                errors.append(f"upsert_failed:{exc}")
    if delete_ids:
        try:
            deleted = delete_catalog_products(list(delete_ids))
        except Exception as exc:
            errors.append(f"delete_failed:{exc}")
    return {"upserted": upserted, "deleted": deleted, "errors": errors}


@router.get("/catalog/products")
def list_products(page: int = 1, page_size: int = 20, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = [{"id": p.id, "sku": p.sku, "brand": p.brand, "name": p.name, "category_id": p.category_id, "attributes": p.attributes, "is_active": p.is_active} for p in db.scalars(select(ProductCatalog)).all()]
    return paginate(rows, page, page_size)


@router.post("/catalog/products")
def create_product(payload: ProductIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if db.scalar(select(ProductCatalog).where(ProductCatalog.sku == payload.sku)):
        raise HTTPException(status_code=400, detail=error_payload("sku_already_exists", "SKU already exists"))
    p = ProductCatalog(**payload.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    vector_sync = _sync_catalog_vectors(db, upsert_ids={p.id} if p.is_active else None)
    return {"id": p.id, **payload.model_dump(), "vector_index": vector_sync}


@router.put("/catalog/products/{product_id}")
def update_product(product_id: str, payload: ProductIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    p = db.get(ProductCatalog, product_id)
    if not p:
        raise HTTPException(status_code=404, detail=error_payload("product_not_found", "Product not found"))
    for key, value in payload.model_dump().items():
        setattr(p, key, value)
    db.commit()
    vector_sync = _sync_catalog_vectors(db, upsert_ids={p.id} if p.is_active else None, delete_ids={p.id} if not p.is_active else None)
    return {"id": p.id, **payload.model_dump(), "vector_index": vector_sync}


@router.delete("/catalog/products/{product_id}")
def delete_product(product_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    p = db.get(ProductCatalog, product_id)
    if not p:
        raise HTTPException(status_code=404, detail=error_payload("product_not_found", "Product not found"))
    p.is_active = False
    db.commit()
    vector_sync = _sync_catalog_vectors(db, delete_ids={p.id})
    return {"success": True, "vector_index": vector_sync}


@router.post("/catalog/import")
def import_catalog(file: UploadFile = File(...), db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    payload = file.file.read()
    try:
        rows = parse_table_bytes(file.filename, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=error_payload("invalid_import_format", str(exc))) from exc
    created = 0
    updated = 0
    skipped = 0
    errors: list[dict] = []
    upsert_ids: set[str] = set()
    delete_ids: set[str] = set()
    category_cache: dict[str, ProductCategory] = {}
    parsed_rows: dict[str, dict] = {}
    for idx, row in enumerate(rows, start=2):
        normalized = {str(k).strip().lower(): v for k, v in row.items()}
        sku = _as_text(normalized.get("sku") or normalized.get("артикул") or normalized.get("код"))
        name = _as_text(normalized.get("name") or normalized.get("наименование") or normalized.get("номенклатура"))
        brand = _as_text(normalized.get("brand") or normalized.get("бренд") or normalized.get("производитель")) or "SANEXT"
        category_name = _as_text(normalized.get("category") or normalized.get("категория") or normalized.get("группа товара"))
        if not sku or not name or not brand:
            skipped += 1
            errors.append({"row": idx, "reason": "missing_required_fields", "fields": ["sku", "name", "brand"]})
            continue
        raw_attrs = normalized.get("attrs_json") or normalized.get("attributes")
        attrs_json = {"raw": str(raw_attrs)} if raw_attrs else {
            k: v
            for k, v in normalized.items()
            if k not in {"sku", "артикул", "код", "name", "наименование", "номенклатура", "brand", "бренд", "производитель", "category", "категория", "группа товара"}
            and v is not None
            and str(v).strip() != ""
        }
        if sku in parsed_rows:
            # last duplicate row in file wins; keep import robust for real-world price lists
            skipped += 1
            errors.append({"row": idx, "reason": "duplicate_sku_in_file", "sku": sku})
        parsed_rows[sku] = {
            "sku": sku,
            "name": name,
            "brand": brand,
            "category_name": category_name,
            "attrs_json": attrs_json,
            "is_active": to_bool(normalized.get("is_active"), True),
        }

    for data in parsed_rows.values():
        category_id = None
        if data["category_name"]:
            category = category_cache.get(data["category_name"]) or db.scalar(
                select(ProductCategory).where(ProductCategory.name == data["category_name"])
            )
            if not category:
                category = ProductCategory(name=data["category_name"])
                db.add(category)
                db.flush()
            category_cache[data["category_name"]] = category
            category_id = category.id

        product = db.scalar(select(ProductCatalog).where(ProductCatalog.sku == data["sku"]))
        if product:
            product.brand = data["brand"]
            product.name = data["name"]
            product.category_id = category_id
            product.attributes = data["attrs_json"] or product.attributes
            product.is_active = data["is_active"]
            if product.is_active:
                upsert_ids.add(product.id)
                delete_ids.discard(product.id)
            else:
                delete_ids.add(product.id)
                upsert_ids.discard(product.id)
            updated += 1
        else:
            item = ProductCatalog(
                sku=data["sku"],
                brand=data["brand"],
                name=data["name"],
                category_id=category_id,
                attributes=data["attrs_json"],
                is_active=data["is_active"],
            )
            db.add(item)
            db.flush()
            if item.is_active:
                upsert_ids.add(item.id)
            created += 1
    report = _store_import_report(
        db,
        "catalog",
        file.filename,
        admin.id,
        len(rows),
        created,
        updated,
        skipped,
        errors,
    )
    db.commit()
    vector_sync = _sync_catalog_vectors(db, upsert_ids=upsert_ids, delete_ids=delete_ids)
    return {
        "success": True,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "total_rows": len(rows),
        "errors": errors[:100],
        "report_id": report.id,
        "vector_index": vector_sync,
    }


@router.post("/catalog/reindex")
def reindex_catalog_vectors(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    products = db.scalars(select(ProductCatalog).where(ProductCatalog.is_active.is_(True))).all()
    try:
        indexed = reindex_catalog(products)
        return {"success": True, "indexed": indexed, "collection": settings.qdrant_collection}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=error_payload("vector_reindex_failed", str(exc))) from exc


@router.get("/analogs")
def list_analogs(page: int = 1, page_size: int = 20, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = [{"id": x.id, "product_id": x.product_id, "analog_product_id": x.analog_product_id, "source": x.source, "confidence": x.confidence, "is_active": x.is_active} for x in db.scalars(select(AnalogMapping)).all()]
    return paginate(rows, page, page_size)


@router.post("/analogs")
def create_analog(payload: AnalogIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if payload.product_id == payload.analog_product_id:
        raise HTTPException(status_code=400, detail=error_payload("self_reference_forbidden", "Product cannot map to itself"))
    item = AnalogMapping(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, **payload.model_dump()}


@router.put("/analogs/{mapping_id}")
def update_analog(mapping_id: str, payload: AnalogIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    item = db.get(AnalogMapping, mapping_id)
    if not item:
        raise HTTPException(status_code=404, detail=error_payload("analog_not_found", "Analog mapping not found"))
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    return {"id": item.id, **payload.model_dump()}


@router.delete("/analogs/{mapping_id}")
def delete_analog(mapping_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    item = db.get(AnalogMapping, mapping_id)
    if not item:
        raise HTTPException(status_code=404, detail=error_payload("analog_not_found", "Analog mapping not found"))
    item.is_active = False
    db.commit()
    return {"success": True}


@router.get("/competitor-mappings")
def list_competitor_mappings(page: int = 1, page_size: int = 20, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = [
        {
            "id": x.id,
            "our_product_id": x.our_product_id,
            "competitor_brand": x.competitor_brand,
            "competitor_name": x.competitor_name,
            "competitor_sku": x.competitor_sku,
            "match_type": x.match_type,
            "confidence": x.confidence,
            "source": x.source,
            "is_active": x.is_active,
        }
        for x in db.scalars(select(CompetitorMapping)).all()
    ]
    return paginate(rows, page, page_size)


@router.post("/competitor-mappings")
def create_competitor_mapping(payload: CompetitorMappingIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if not db.get(ProductCatalog, payload.our_product_id):
        raise HTTPException(status_code=404, detail=error_payload("product_not_found", "Our product not found"))
    item = CompetitorMapping(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, **payload.model_dump()}


@router.post("/competitor-mappings/import")
def import_competitor_mappings(file: UploadFile = File(...), db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    payload = file.file.read()
    try:
        rows = parse_table_bytes(file.filename, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=error_payload("invalid_import_format", str(exc))) from exc
    created = 0
    updated = 0
    skipped = 0
    errors: list[dict] = []
    for idx, row in enumerate(rows, start=2):
        normalized = {str(k).strip().lower(): v for k, v in row.items()}
        our_sku = _as_text(normalized.get("our_sku") or normalized.get("sku"))
        competitor_brand = _as_text(normalized.get("competitor_brand") or normalized.get("бренд_конкурента"))
        competitor_name = _as_text(normalized.get("competitor_name") or normalized.get("наименование_конкурента"))
        competitor_sku = _as_text(normalized.get("competitor_sku") or normalized.get("артикул_конкурента")) or None
        if not our_sku or not competitor_brand or not competitor_name:
            skipped += 1
            errors.append({"row": idx, "reason": "missing_required_fields", "fields": ["our_sku", "competitor_brand", "competitor_name"]})
            continue
        our_product = db.scalar(select(ProductCatalog).where(ProductCatalog.sku == our_sku))
        if not our_product:
            skipped += 1
            errors.append({"row": idx, "reason": "our_sku_not_found", "our_sku": our_sku})
            continue
        match_type = (normalized.get("match_type") or "analog").strip()
        source = (normalized.get("source") or "import").strip()
        confidence = to_float(normalized.get("confidence"), 0.8)
        is_active = to_bool(normalized.get("is_active"), True)
        existing = db.scalar(
            select(CompetitorMapping).where(
                CompetitorMapping.our_product_id == our_product.id,
                CompetitorMapping.competitor_brand == competitor_brand,
                CompetitorMapping.competitor_name == competitor_name,
                CompetitorMapping.competitor_sku == competitor_sku,
            )
        )
        if existing:
            existing.match_type = match_type
            existing.confidence = confidence
            existing.source = source
            existing.is_active = is_active
            updated += 1
        else:
            db.add(
                CompetitorMapping(
                    our_product_id=our_product.id,
                    competitor_brand=competitor_brand,
                    competitor_name=competitor_name,
                    competitor_sku=competitor_sku,
                    match_type=match_type,
                    confidence=confidence,
                    source=source,
                    is_active=is_active,
                )
            )
            created += 1
    report = _store_import_report(
        db,
        "competitor_mappings",
        file.filename,
        admin.id,
        len(rows),
        created,
        updated,
        skipped,
        errors,
    )
    db.commit()
    return {
        "success": True,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "total_rows": len(rows),
        "errors": errors[:100],
        "report_id": report.id,
    }


@router.get("/import-reports")
def list_import_reports(page: int = 1, page_size: int = 20, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    reports = db.scalars(select(ImportReport).order_by(ImportReport.created_at.desc())).all()
    rows = [
        {
            "id": r.id,
            "report_type": r.report_type,
            "filename": r.filename,
            "total_rows": r.total_rows,
            "created_count": r.created_count,
            "updated_count": r.updated_count,
            "skipped_count": r.skipped_count,
            "error_count": len(r.errors or []),
            "created_at": r.created_at.isoformat(),
        }
        for r in reports
    ]
    return paginate(rows, page, page_size)


@router.get("/import-reports/{report_id}")
def get_import_report(report_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    report = db.get(ImportReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail=error_payload("import_report_not_found", "Import report not found"))
    return {
        "id": report.id,
        "report_type": report.report_type,
        "filename": report.filename,
        "total_rows": report.total_rows,
        "created_count": report.created_count,
        "updated_count": report.updated_count,
        "skipped_count": report.skipped_count,
        "errors": report.errors or [],
        "created_at": report.created_at.isoformat(),
    }


@router.get("/import-reports/{report_id}/export")
def export_import_report(report_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    report = db.get(ImportReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail=error_payload("import_report_not_found", "Import report not found"))
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["row", "reason", "fields", "our_sku"])
    writer.writeheader()
    for item in report.errors or []:
        writer.writerow(
            {
                "row": item.get("row"),
                "reason": item.get("reason"),
                "fields": ",".join(item.get("fields", [])) if isinstance(item.get("fields"), list) else item.get("fields"),
                "our_sku": item.get("our_sku"),
            }
        )
    data = output.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=import_report_{report_id}.csv"},
    )


@router.get("/templates/catalog")
def catalog_template(admin: User = Depends(require_admin)):
    wb = Workbook()
    ws = wb.active
    ws.title = "catalog_import"
    ws.append(["sku", "name", "brand", "category", "is_active", "attrs_json"])
    ws.append(["GR-CR3-15", "Grundfos CR 3-15 Pump", "Grundfos", "Pumps", "true", '{"power_kw":1.5,"voltage_v":380}'])
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="catalog_template.xlsx"'},
    )


@router.get("/templates/competitor-mappings")
def competitor_template(admin: User = Depends(require_admin)):
    wb = Workbook()
    ws = wb.active
    ws.title = "competitor_mappings"
    ws.append(["our_sku", "competitor_brand", "competitor_name", "competitor_sku", "match_type", "confidence", "source", "is_active"])
    ws.append(["GR-CR3-15", "CompetitorX", "Pump X 3-15", "CX-315", "analog", 0.86, "import", "true"])
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="competitor_mappings_template.xlsx"'},
    )


@router.get("/rules")
def list_rules(page: int = 1, page_size: int = 20, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = [{"id": x.id, "name": x.name, "priority": x.priority, "is_active": x.is_active, "conditions": x.conditions, "actions": x.actions} for x in db.scalars(select(MatchingRule)).all()]
    return paginate(rows, page, page_size)


@router.get("/matching/stop-words")
def list_stop_words(admin: User = Depends(require_admin)):
    return {"items": load_stop_words()}


@router.put("/matching/stop-words")
def update_stop_words(payload: StopWordsIn, admin: User = Depends(require_admin)):
    items = save_stop_words(payload.words)
    return {"success": True, "items": items, "count": len(items)}


@router.get("/matching/catalog-rules")
def list_catalog_rules(admin: User = Depends(require_admin)):
    items = list_catalog_match_rules()
    return {"items": items, "count": len(items)}


@router.post("/matching/catalog-rules")
def create_catalog_rule(payload: CatalogMatchRuleIn, admin: User = Depends(require_admin)):
    when_all = [x.strip() for x in payload.when_all if str(x).strip()]
    require_any = [x.strip() for x in payload.require_any if str(x).strip()]
    if not when_all or not require_any:
        raise HTTPException(
            status_code=400,
            detail=error_payload(
                "invalid_catalog_rule",
                "Both when_all and require_any must contain at least one value",
            ),
        )
    try:
        item = add_catalog_match_rule(payload.annotation, when_all, require_any)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=error_payload("invalid_catalog_rule", str(exc))) from exc
    return {"success": True, "item": item}


@router.delete("/matching/catalog-rules/{rule_id}")
def remove_catalog_rule(rule_id: str, admin: User = Depends(require_admin)):
    removed = delete_catalog_match_rule(rule_id)
    if not removed:
        raise HTTPException(status_code=404, detail=error_payload("catalog_rule_not_found", "Catalog rule not found"))
    return {"success": True}


@router.put("/matching/catalog-rules/{rule_id}")
def edit_catalog_rule(rule_id: str, payload: CatalogMatchRuleIn, admin: User = Depends(require_admin)):
    when_all = [x.strip() for x in payload.when_all if str(x).strip()]
    require_any = [x.strip() for x in payload.require_any if str(x).strip()]
    if not when_all or not require_any:
        raise HTTPException(
            status_code=400,
            detail=error_payload(
                "invalid_catalog_rule",
                "Both when_all and require_any must contain at least one value",
            ),
        )
    try:
        item = update_catalog_match_rule(rule_id, payload.annotation, when_all, require_any)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=error_payload("invalid_catalog_rule", str(exc))) from exc
    if item is None:
        raise HTTPException(status_code=404, detail=error_payload("catalog_rule_not_found", "Catalog rule not found"))
    return {"success": True, "item": item}


@router.post("/rules")
def create_rule(payload: RuleIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if db.scalar(select(MatchingRule).where(MatchingRule.name == payload.name)):
        raise HTTPException(status_code=400, detail=error_payload("rule_name_conflict", "Rule name already exists"))
    item = MatchingRule(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, **payload.model_dump()}


@router.put("/rules/{rule_id}")
def update_rule(rule_id: str, payload: RuleIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    item = db.get(MatchingRule, rule_id)
    if not item:
        raise HTTPException(status_code=404, detail=error_payload("rule_not_found", "Rule not found"))
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    return {"id": item.id, **payload.model_dump()}


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    item = db.get(MatchingRule, rule_id)
    if not item:
        raise HTTPException(status_code=404, detail=error_payload("rule_not_found", "Rule not found"))
    item.is_active = False
    db.commit()
    return {"success": True}
