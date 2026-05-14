from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import ProductCatalog, ProductCategory, Role, User
from app.modules.admin.api import router as admin_router
from app.modules.auth.api import router as auth_router
from app.modules.catalog.api import router as catalog_router
from app.modules.export.api import router as export_router
from app.modules.files.api import router as files_router
from app.modules.history.api import router as history_router
from app.modules.matching.api import router as matching_router
from app.modules.parsing.api import router as parsing_router
from app.modules.requests.api import router as requests_router
from app.modules.results.api import router as results_router

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(catalog_router, prefix="/api/v1")
app.include_router(requests_router, prefix="/api/v1")
app.include_router(files_router, prefix="/api/v1")
app.include_router(parsing_router, prefix="/api/v1")
app.include_router(matching_router, prefix="/api/v1")
app.include_router(results_router, prefix="/api/v1")
app.include_router(export_router, prefix="/api/v1")
app.include_router(history_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")


def _ensure_roles(db) -> None:
    if db.scalar(select(Role)):
        return
    db.add_all([Role(name="admin"), Role(name="operator"), Role(name="reviewer")])
    db.commit()


def seed_data() -> None:
    with SessionLocal() as db:
        _ensure_roles(db)
        if not settings.seed_demo_users:
            return
        if db.scalar(select(User).where(User.email == "admin@local")):
            return
        admin = User(
            email="admin@local",
            password_hash=hash_password("admin123"),
            full_name="Admin",
            is_admin=True,
        )
        operator = User(
            email="operator@local",
            password_hash=hash_password("operator123"),
            full_name="Operator",
            is_admin=False,
        )
        category = ProductCategory(name="Pumps")
        db.add_all([admin, operator, category])
        db.flush()
        db.add_all(
            [
                ProductCatalog(sku="GR-CR3-15", brand="Grundfos", name="Grundfos CR 3-15 Pump", category_id=category.id, attributes={"power_kw": 1.5}),
                ProductCatalog(sku="WILO-25", brand="Wilo", name="Wilo Star RS 25", category_id=category.id, attributes={"power_kw": 0.7}),
                ProductCatalog(sku="KSB-100", brand="KSB", name="KSB Etanorm 100", category_id=category.id, attributes={"power_kw": 2.2}),
            ]
        )
        db.commit()


@app.on_event("startup")
def startup() -> None:
    Path(settings.storage_root).mkdir(parents=True, exist_ok=True)
    seed_data()


app.mount("/", StaticFiles(directory="web", html=True), name="web")
