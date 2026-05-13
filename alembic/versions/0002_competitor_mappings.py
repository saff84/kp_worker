"""add competitor mappings

Revision ID: 0002_competitor_mappings
Revises: 0001_initial
Create Date: 2026-04-23
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_competitor_mappings"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "competitor_mappings",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("our_product_id", sa.String(length=64), sa.ForeignKey("product_catalog.id"), nullable=False),
        sa.Column("competitor_brand", sa.String(length=255), nullable=False),
        sa.Column("competitor_name", sa.String(length=255), nullable=False),
        sa.Column("competitor_sku", sa.String(length=255), nullable=True),
        sa.Column("match_type", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_competitor_mappings_our_product_id", "competitor_mappings", ["our_product_id"])
    op.create_index("ix_competitor_mappings_competitor_brand", "competitor_mappings", ["competitor_brand"])
    op.create_index("ix_competitor_mappings_competitor_sku", "competitor_mappings", ["competitor_sku"])


def downgrade() -> None:
    op.drop_index("ix_competitor_mappings_competitor_sku", table_name="competitor_mappings")
    op.drop_index("ix_competitor_mappings_competitor_brand", table_name="competitor_mappings")
    op.drop_index("ix_competitor_mappings_our_product_id", table_name="competitor_mappings")
    op.drop_table("competitor_mappings")
