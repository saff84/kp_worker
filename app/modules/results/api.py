from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import error_payload
from app.db.session import get_db
from app.models import ApprovedMatch, MatchResult, ParsedItem, ProductCatalog, RequestItem, User
from app.shared.pagination import paginate

router = APIRouter(prefix="/requests/{request_id}/results", tags=["results"])


class ManualReviewIn(BaseModel):
    action: str
    selected_product_id: str | None = None
    comment: str | None = None


@router.get("")
def get_results(
    request_id: str,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    req = db.get(RequestItem, request_id)
    if not req:
        raise HTTPException(status_code=404, detail=error_payload("request_not_found", "Request not found"))
    rows = []
    items = db.scalars(select(ParsedItem).where(ParsedItem.request_id == request_id)).all()
    for item in items:
        best = db.scalar(
            select(MatchResult)
            .where(MatchResult.request_id == request_id, MatchResult.parsed_item_id == item.id)
            .order_by(MatchResult.score.desc())
        )
        if not best:
            continue
        if status and best.status != status:
            continue
        product = db.get(ProductCatalog, best.candidate_product_id) if best.candidate_product_id else None
        alternatives = db.scalars(select(MatchResult).where(MatchResult.request_id == request_id, MatchResult.parsed_item_id == item.id)).all()
        alt_product_ids = [x.candidate_product_id for x in alternatives if x.candidate_product_id]
        alt_products = {p.id: p for p in db.scalars(select(ProductCatalog).where(ProductCatalog.id.in_(alt_product_ids))).all()} if alt_product_ids else {}
        rows.append(
            {
                "parsed_item_id": item.id,
                "source": {"item_name": item.item_name, "article": item.article, "brand": item.brand, "quantity": item.quantity},
                "match": {
                    "status": best.status,
                    "best_candidate": {
                        "product_id": product.id if product else None,
                        "sku": product.sku if product else None,
                        "name": product.name if product else None,
                        "score": best.score,
                        "reason": best.explanation.get("reasons", []),
                    },
                    "candidates": [
                        {
                            "product_id": x.candidate_product_id,
                            "score": x.score,
                            "sku": alt_products.get(x.candidate_product_id).sku if x.candidate_product_id and alt_products.get(x.candidate_product_id) else None,
                            "name": alt_products.get(x.candidate_product_id).name if x.candidate_product_id and alt_products.get(x.candidate_product_id) else None,
                            "brand": alt_products.get(x.candidate_product_id).brand if x.candidate_product_id and alt_products.get(x.candidate_product_id) else None,
                        }
                        for x in alternatives
                    ],
                },
            }
        )
    return paginate(rows, page, page_size)


@router.put("/{parsed_item_id}")
def update_result(request_id: str, parsed_item_id: str, payload: ManualReviewIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    req = db.get(RequestItem, request_id)
    if not req:
        raise HTTPException(status_code=404, detail=error_payload("request_not_found", "Request not found"))
    if payload.action not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail=error_payload("invalid_action", "Action must be approve or reject"))
    if payload.action == "approve":
        if not payload.selected_product_id:
            raise HTTPException(status_code=400, detail=error_payload("validation_error", "selected_product_id required"))
        product = db.get(ProductCatalog, payload.selected_product_id)
        if not product:
            raise HTTPException(status_code=404, detail=error_payload("product_not_found", "Product not found"))
        existing = db.scalar(select(ApprovedMatch).where(ApprovedMatch.parsed_item_id == parsed_item_id))
        if existing:
            existing.product_id = product.id
            existing.approved_by = current.id
            existing.approval_source = "manual"
            existing.note = payload.comment
        else:
            db.add(
                ApprovedMatch(
                    request_id=request_id,
                    parsed_item_id=parsed_item_id,
                    product_id=product.id,
                    approved_by=current.id,
                    approval_source="manual",
                    note=payload.comment,
                )
            )
        status = "approved"
    else:
        status = "rejected"
    match = db.scalar(select(MatchResult).where(MatchResult.parsed_item_id == parsed_item_id))
    if match:
        match.status = "auto_matched" if payload.action == "approve" else "rejected"
    db.commit()
    return {
        "request_id": request_id,
        "parsed_item_id": parsed_item_id,
        "status": status,
        "approved_match": {
            "product_id": payload.selected_product_id,
            "approved_by": current.id,
            "approved_at": datetime.now(timezone.utc).isoformat(),
        },
    }
