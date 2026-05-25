"""make defense_lawyer_id nullable for PDF-imported cases

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "cases",
        "defense_lawyer_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    # Re-assign NULLs before restoring NOT NULL constraint
    op.execute(
        "UPDATE cases SET defense_lawyer_id = "
        "(SELECT id FROM lawyers ORDER BY id LIMIT 1) "
        "WHERE defense_lawyer_id IS NULL"
    )
    op.alter_column(
        "cases",
        "defense_lawyer_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
