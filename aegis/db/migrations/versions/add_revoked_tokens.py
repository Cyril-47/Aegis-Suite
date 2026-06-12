"""add revoked tokens table

Revision ID: add_revoked_tokens
Revises: baseline_v1
Create Date: 2026-06-12 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_revoked_tokens'
down_revision: Union[str, None] = 'baseline_v1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "revoked_tokens",
        sa.Column("token", sa.String(), primary_key=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_table("revoked_tokens")
