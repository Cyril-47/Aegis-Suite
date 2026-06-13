"""Add intelligence tables: raid_events, config_snapshots, server_benchmarks

Revision ID: add_intelligence_tables
Revises: add_revoked_tokens
Create Date: 2026-06-12 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_intelligence_tables'
down_revision: Union[str, None] = 'add_revoked_tokens'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'raid_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('guild_id', sa.String(), nullable=False),
        sa.Column('detected_at', sa.DateTime(), nullable=True),
        sa.Column('join_count', sa.Integer(), nullable=False),
        sa.Column('window_seconds', sa.Integer(), nullable=False),
        sa.Column('response_action', sa.String(), nullable=False),
        sa.Column('members_affected', sa.Text(), nullable=True),
        sa.Column('resolved', sa.Integer(), server_default='0'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_raid_events_guild_id', 'raid_events', ['guild_id'])

    op.create_table(
        'config_snapshots',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('guild_id', sa.String(), nullable=False),
        sa.Column('config_json', sa.Text(), nullable=False),
        sa.Column('change_summary', sa.String(), nullable=True),
        sa.Column('changed_keys', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_config_snapshots_guild_id', 'config_snapshots', ['guild_id'])

    op.create_table(
        'server_benchmarks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('guild_id', sa.String(), nullable=False),
        sa.Column('date', sa.DateTime(), nullable=False),
        sa.Column('avg_messages_per_day', sa.Integer(), server_default='0'),
        sa.Column('avg_active_users', sa.Integer(), server_default='0'),
        sa.Column('avg_voice_minutes', sa.Integer(), server_default='0'),
        sa.Column('mod_actions_per_week', sa.Integer(), server_default='0'),
        sa.Column('health_score', sa.Integer(), server_default='0'),
        sa.Column('engagement_percentile', sa.Integer(), server_default='0'),
        sa.Column('moderation_percentile', sa.Integer(), server_default='0'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_server_benchmarks_guild_id', 'server_benchmarks', ['guild_id'])


def downgrade() -> None:
    op.drop_index('ix_server_benchmarks_guild_id', table_name='server_benchmarks')
    op.drop_table('server_benchmarks')
    op.drop_index('ix_config_snapshots_guild_id', table_name='config_snapshots')
    op.drop_table('config_snapshots')
    op.drop_index('ix_raid_events_guild_id', table_name='raid_events')
    op.drop_table('raid_events')
