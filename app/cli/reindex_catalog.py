from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ProductCatalog
from app.services.hybrid_search import reindex_catalog


def main() -> None:
    with SessionLocal() as db:
        products = db.scalars(select(ProductCatalog).where(ProductCatalog.is_active.is_(True))).all()
    indexed = reindex_catalog(products)
    print(f"Reindexed {indexed} active catalog products")


if __name__ == "__main__":
    main()
