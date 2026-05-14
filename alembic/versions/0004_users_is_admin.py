"""users is_admin flag

Revision ID: 0004_users_is_admin
Revises: 0003_import_reports
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_users_is_admin"
down_revision = "0003_import_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.execute("UPDATE users SET is_admin = true WHERE lower(email) = 'admin@local'")


def downgrade() -> None:
    op.drop_column("users", "is_admin")
