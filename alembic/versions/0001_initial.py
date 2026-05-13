"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-23
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table("roles", sa.Column("id", sa.String(length=64), primary_key=True), sa.Column("name", sa.String(length=64), nullable=False, unique=True))
    op.create_index("ix_roles_name", "roles", ["name"], unique=True)

    op.create_table(
        "requests",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("created_by", sa.String(length=64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("input_text", sa.Text(), nullable=True),
        sa.Column("parse_status", sa.String(length=32), nullable=False),
        sa.Column("match_status", sa.String(length=32), nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("matched_items", sa.Integer(), nullable=False),
        sa.Column("needs_review_items", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_requests_created_by", "requests", ["created_by"])
    op.create_index("ix_requests_status", "requests", ["status"])

    op.create_table(
        "uploaded_files",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("request_id", sa.String(length=64), sa.ForeignKey("requests.id"), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_uploaded_files_request_id", "uploaded_files", ["request_id"])

    op.create_table(
        "parsed_items",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("request_id", sa.String(length=64), sa.ForeignKey("requests.id"), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("item_name", sa.String(length=255), nullable=True),
        sa.Column("article", sa.String(length=255), nullable=True),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("specs", sa.JSON(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("parse_confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_parsed_items_request_id", "parsed_items", ["request_id"])
    op.create_index("ix_parsed_items_article", "parsed_items", ["article"])
    op.create_index("ix_parsed_items_brand", "parsed_items", ["brand"])

    op.create_table("product_categories", sa.Column("id", sa.String(length=64), primary_key=True), sa.Column("name", sa.String(length=255), unique=True, nullable=False))

    op.create_table(
        "product_catalog",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("category_id", sa.String(length=64), sa.ForeignKey("product_categories.id"), nullable=True),
        sa.Column("sku", sa.String(length=255), nullable=False, unique=True),
        sa.Column("brand", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_product_catalog_sku", "product_catalog", ["sku"], unique=True)
    op.create_index("ix_product_catalog_brand", "product_catalog", ["brand"])
    op.create_index("ix_product_catalog_category_id", "product_catalog", ["category_id"])
    op.create_index("ix_product_catalog_is_active", "product_catalog", ["is_active"])

    op.create_table(
        "analog_mappings",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("product_id", sa.String(length=64), sa.ForeignKey("product_catalog.id"), nullable=False),
        sa.Column("analog_product_id", sa.String(length=64), sa.ForeignKey("product_catalog.id"), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_analog_mappings_product_id", "analog_mappings", ["product_id"])
    op.create_index("ix_analog_mappings_analog_product_id", "analog_mappings", ["analog_product_id"])

    op.create_table(
        "matching_rules",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False),
    )

    op.create_table(
        "match_results",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("request_id", sa.String(length=64), sa.ForeignKey("requests.id"), nullable=False),
        sa.Column("parsed_item_id", sa.String(length=64), sa.ForeignKey("parsed_items.id"), nullable=False),
        sa.Column("candidate_product_id", sa.String(length=64), sa.ForeignKey("product_catalog.id"), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("explanation", sa.JSON(), nullable=False),
    )
    op.create_index("ix_match_results_request_id", "match_results", ["request_id"])
    op.create_index("ix_match_results_parsed_item_id", "match_results", ["parsed_item_id"])
    op.create_index("ix_match_results_status", "match_results", ["status"])

    op.create_table(
        "approved_matches",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("request_id", sa.String(length=64), sa.ForeignKey("requests.id"), nullable=False),
        sa.Column("parsed_item_id", sa.String(length=64), sa.ForeignKey("parsed_items.id"), nullable=False, unique=True),
        sa.Column("product_id", sa.String(length=64), sa.ForeignKey("product_catalog.id"), nullable=False),
        sa.Column("approved_by", sa.String(length=64), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approval_source", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_approved_matches_request_id", "approved_matches", ["request_id"])

    op.create_table(
        "export_files",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("request_id", sa.String(length=64), sa.ForeignKey("requests.id"), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False, unique=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_export_files_request_id", "export_files", ["request_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor_user_id", sa.String(length=64), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=64), sa.ForeignKey("requests.id"), nullable=True),
        sa.Column("event_meta", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_index("ix_export_files_request_id", table_name="export_files")
    op.drop_table("export_files")
    op.drop_index("ix_approved_matches_request_id", table_name="approved_matches")
    op.drop_table("approved_matches")
    op.drop_index("ix_match_results_status", table_name="match_results")
    op.drop_index("ix_match_results_parsed_item_id", table_name="match_results")
    op.drop_index("ix_match_results_request_id", table_name="match_results")
    op.drop_table("match_results")
    op.drop_table("matching_rules")
    op.drop_index("ix_analog_mappings_analog_product_id", table_name="analog_mappings")
    op.drop_index("ix_analog_mappings_product_id", table_name="analog_mappings")
    op.drop_table("analog_mappings")
    op.drop_index("ix_product_catalog_is_active", table_name="product_catalog")
    op.drop_index("ix_product_catalog_category_id", table_name="product_catalog")
    op.drop_index("ix_product_catalog_brand", table_name="product_catalog")
    op.drop_index("ix_product_catalog_sku", table_name="product_catalog")
    op.drop_table("product_catalog")
    op.drop_table("product_categories")
    op.drop_index("ix_parsed_items_brand", table_name="parsed_items")
    op.drop_index("ix_parsed_items_article", table_name="parsed_items")
    op.drop_index("ix_parsed_items_request_id", table_name="parsed_items")
    op.drop_table("parsed_items")
    op.drop_index("ix_uploaded_files_request_id", table_name="uploaded_files")
    op.drop_table("uploaded_files")
    op.drop_index("ix_requests_status", table_name="requests")
    op.drop_index("ix_requests_created_by", table_name="requests")
    op.drop_table("requests")
    op.drop_index("ix_roles_name", table_name="roles")
    op.drop_table("roles")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
