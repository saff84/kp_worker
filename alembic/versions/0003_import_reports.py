"""add import reports

Revision ID: 0003_import_reports
Revises: 0002_competitor_mappings
Create Date: 2026-04-23
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_import_reports"
down_revision = "0002_competitor_mappings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_reports",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("report_type", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("created_by", sa.String(length=64), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("created_count", sa.Integer(), nullable=False),
        sa.Column("updated_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_import_reports_report_type", "import_reports", ["report_type"])


def downgrade() -> None:
    op.drop_index("ix_import_reports_report_type", table_name="import_reports")
    op.drop_table("import_reports")
