"""baseline v1 migration

Revision ID: baseline_v1
Revises: None
Create Date: 2026-05-31 20:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'baseline_v1'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "schema_meta",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.String(), nullable=True)
    )
    op.create_table(
        "config_kv",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True)
    )
    op.create_table(
        "templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("json", sa.Text(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True)
    )
    op.create_table(
        "servers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("guild_id", sa.String(), unique=True, nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("mode", sa.String(), nullable=True),
        sa.Column("last_synced", sa.DateTime(), nullable=True)
    )
    op.create_table(
        "apply_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("server_id", sa.Integer(), sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True)
    )
    op.create_table(
        "migration_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("from_rev", sa.String(), nullable=True),
        sa.Column("to_rev", sa.String(), nullable=True),
        sa.Column("backup_path", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_table("migration_log")
    op.drop_table("apply_history")
    op.drop_table("servers")
    op.drop_table("templates")
    op.drop_table("config_kv")
    op.drop_table("schema_meta")
