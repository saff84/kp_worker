from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)


class RequestItem(Base):
    __tablename__ = "requests"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    created_by: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="uploaded", index=True)
    source_type: Mapped[str] = mapped_column(String(16), default="text")
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parse_status: Mapped[str] = mapped_column(String(32), default="not_started")
    match_status: Mapped[str] = mapped_column(String(32), default="not_started")
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    matched_items: Mapped[int] = mapped_column(Integer, default=0)
    needs_review_items: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    request_id: Mapped[str] = mapped_column(String(64), ForeignKey("requests.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ParsedItem(Base):
    __tablename__ = "parsed_items"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    request_id: Mapped[str] = mapped_column(String(64), ForeignKey("requests.id"), index=True)
    raw_text: Mapped[str] = mapped_column(Text)
    item_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    article: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    specs: Mapped[dict] = mapped_column(JSON, default=dict)
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    parse_confidence: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ProductCategory(Base):
    __tablename__ = "product_categories"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), unique=True)


class ProductCatalog(Base):
    __tablename__ = "product_catalog"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    category_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("product_categories.id"), nullable=True, index=True)
    sku: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    brand: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255))
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class AnalogMapping(Base):
    __tablename__ = "analog_mappings"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    product_id: Mapped[str] = mapped_column(String(64), ForeignKey("product_catalog.id"), index=True)
    analog_product_id: Mapped[str] = mapped_column(String(64), ForeignKey("product_catalog.id"), index=True)
    source: Mapped[str] = mapped_column(String(64), default="manual")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class CompetitorMapping(Base):
    __tablename__ = "competitor_mappings"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    our_product_id: Mapped[str] = mapped_column(String(64), ForeignKey("product_catalog.id"), index=True)
    competitor_brand: Mapped[str] = mapped_column(String(255), index=True)
    competitor_name: Mapped[str] = mapped_column(String(255))
    competitor_sku: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    match_type: Mapped[str] = mapped_column(String(32), default="analog")
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    source: Mapped[str] = mapped_column(String(64), default="import")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ImportReport(Base):
    __tablename__ = "import_reports"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    report_type: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    created_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id"), nullable=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class MatchingRule(Base):
    __tablename__ = "matching_rules"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), unique=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    conditions: Mapped[dict] = mapped_column(JSON, default=dict)
    actions: Mapped[dict] = mapped_column(JSON, default=dict)


class MatchResult(Base):
    __tablename__ = "match_results"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    request_id: Mapped[str] = mapped_column(String(64), ForeignKey("requests.id"), index=True)
    parsed_item_id: Mapped[str] = mapped_column(String(64), ForeignKey("parsed_items.id"), index=True)
    candidate_product_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("product_catalog.id"), nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="needs_review", index=True)
    explanation: Mapped[dict] = mapped_column(JSON, default=dict)


class ApprovedMatch(Base):
    __tablename__ = "approved_matches"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    request_id: Mapped[str] = mapped_column(String(64), ForeignKey("requests.id"), index=True)
    parsed_item_id: Mapped[str] = mapped_column(String(64), ForeignKey("parsed_items.id"), unique=True)
    product_id: Mapped[str] = mapped_column(String(64), ForeignKey("product_catalog.id"))
    approved_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id"), nullable=True)
    approval_source: Mapped[str] = mapped_column(String(16), default="auto")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ExportFile(Base):
    __tablename__ = "export_files"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    request_id: Mapped[str] = mapped_column(String(64), ForeignKey("requests.id"), index=True)
    format: Mapped[str] = mapped_column(String(16), default="csv")
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(255))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("requests.id"), nullable=True)
    event_meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
