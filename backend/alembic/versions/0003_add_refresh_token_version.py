"""add_refresh_token_version

Revision ID: 0003_add_refresh_token_version
Revises: 0002_create_users_table
Create Date: 2026-10-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0003_add_refresh_token_version"
down_revision = "0002_create_users_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("refresh_token_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "refresh_token_version")
