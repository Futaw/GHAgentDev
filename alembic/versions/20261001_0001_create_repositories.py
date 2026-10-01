"""Create repositories table.

Revision ID: 20261001_0001
Revises:
Create Date: 2026-10-01
"""

import sqlalchemy as sa

from alembic import op

revision = "20261001_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repositories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner", sa.String(length=39), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("canonical_github_url", sa.String(length=255), nullable=False),
        sa.Column("workspace_key", sa.String(length=36), nullable=False),
        sa.Column("default_branch", sa.String(length=255), nullable=True),
        sa.Column("latest_commit_sha", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'cloning', 'ready', 'syncing', 'failed')",
            name="ck_repositories_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_github_url"),
        sa.UniqueConstraint("workspace_key"),
    )


def downgrade() -> None:
    op.drop_table("repositories")
