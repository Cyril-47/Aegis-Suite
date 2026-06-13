"""add entrants and host_name columns to giveaways

Revision ID: add_giveaway_extras
Revises: add_intelligence_tables
Create Date: 2026-06-12 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_giveaway_extras'
down_revision: Union[str, None] = 'add_intelligence_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    res = bind.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table_name},
    ).fetchone()
    return res is not None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    res = bind.execute(
        sa.text(f"PRAGMA table_info({table_name})"),
    ).fetchall()
    return any(row[1] == column_name for row in res)


def upgrade() -> None:
    if not _table_exists("giveaways"):
        op.create_table(
            "giveaways",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("guild_id", sa.String(), nullable=False),
            sa.Column("message_id", sa.String(), unique=True),
            sa.Column("channel_id", sa.String()),
            sa.Column("prize", sa.String()),
            sa.Column("winner_count", sa.Integer(), server_default="1"),
            sa.Column("end_time", sa.DateTime(), nullable=True),
            sa.Column("host_user_id", sa.String()),
            sa.Column("host_name", sa.String(), nullable=True),
            sa.Column("status", sa.String(), server_default="active"),
            sa.Column("entrants", sa.Text(), nullable=True),
            sa.Column("winners", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_giveaways_guild_id", "giveaways", ["guild_id"])
    else:
        if not _column_exists("giveaways", "entrants"):
            op.add_column("giveaways", sa.Column("entrants", sa.Text(), nullable=True))
        if not _column_exists("giveaways", "host_name"):
            op.add_column("giveaways", sa.Column("host_name", sa.String(), nullable=True))


def downgrade() -> None:
    if _column_exists("giveaways", "host_name"):
        op.drop_column("giveaways", "host_name")
    if _column_exists("giveaways", "entrants"):
        op.drop_column("giveaways", "entrants")
