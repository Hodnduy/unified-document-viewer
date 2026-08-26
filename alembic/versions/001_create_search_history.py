"""Create search_history table.

Revision ID: 001
Revises: None
Create Date: 2026-08-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "search_history",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("vin", sa.String(17), nullable=False, index=True),
        sa.Column(
            "searched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("total_documents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_degraded", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_table("search_history")
