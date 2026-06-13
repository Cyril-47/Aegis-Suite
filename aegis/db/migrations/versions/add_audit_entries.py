"""Add audit_entries table.

Revision ID: add_audit_entries
Revises: add_giveaway_extras
Create Date: 2026-06-12 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_audit_entries'
down_revision: Union[str, None] = 'add_giveaway_extras'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_entries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('guild_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=True),
        sa.Column('action', sa.String(), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_entries_guild_id', 'audit_entries', ['guild_id'])
    op.create_index('ix_audit_entries_user_id', 'audit_entries', ['user_id'])
    op.create_index('ix_audit_entries_action', 'audit_entries', ['action'])


def downgrade() -> None:
    op.drop_index('ix_audit_entries_action', table_name='audit_entries')
    op.drop_index('ix_audit_entries_user_id', table_name='audit_entries')
    op.drop_index('ix_audit_entries_guild_id', table_name='audit_entries')
    op.drop_table('audit_entries')
