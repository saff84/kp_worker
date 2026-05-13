from fastapi import APIRouter, Depends
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import ProductCatalog, User

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/products")
def search_catalog_products(
    query: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    stmt = select(ProductCatalog).where(ProductCatalog.is_active.is_(True))
    if query and query.strip():
        terms = [x.strip() for x in query.strip().split() if x.strip()]
        if terms:
            stmt = stmt.where(
                and_(
                    *[
                        or_(
                            ProductCatalog.sku.ilike(f"%{t}%"),
                            ProductCatalog.name.ilike(f"%{t}%"),
                            ProductCatalog.brand.ilike(f"%{t}%"),
                        )
                        for t in terms
                    ]
                )
            )
        else:
            term = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    ProductCatalog.sku.ilike(term),
                    ProductCatalog.name.ilike(term),
                    ProductCatalog.brand.ilike(term),
                )
            )
    products = db.scalars(stmt.limit(max(1, min(limit, 200)))).all()
    return {
        "items": [
            {
                "id": p.id,
                "sku": p.sku,
                "brand": p.brand,
                "name": p.name,
            }
            for p in products
        ]
    }
