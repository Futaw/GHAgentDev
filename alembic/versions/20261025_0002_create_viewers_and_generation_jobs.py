"""Create viewers and generation jobs.

Revision ID: 20261025_0002
Revises: 20261001_0001
Create Date: 2026-10-25
"""

import sqlalchemy as sa

from alembic import op

revision = "20261025_0002"
down_revision = "20261001_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "viewers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.String(length=1000), nullable=False),
        sa.Column("document_type", sa.String(length=32), nullable=False),
        sa.Column("detail_level", sa.String(length=16), nullable=False),
        sa.Column("target_audience", sa.String(length=32), nullable=False),
        sa.Column("theme_slug", sa.String(length=32), nullable=False),
        sa.Column("density", sa.String(length=16), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("sanitized_html", sa.Text(), nullable=False),
        sa.Column("request", sa.Text(), nullable=False),
        sa.Column("additional_instruction", sa.Text(), nullable=True),
        sa.Column("commit_sha", sa.String(length=64), nullable=False),
        sa.Column("renderer_version", sa.String(length=32), nullable=False),
        sa.Column("content_revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("content_revision >= 1", name="ck_viewers_content_revision"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_viewers_repository_updated", "viewers", ["repository_id", "updated_at"])
    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("viewer_id", sa.Uuid(), nullable=True),
        sa.Column("retry_of_job_id", sa.Uuid(), nullable=True),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("current_phase", sa.String(length=32), nullable=False),
        sa.Column("request", sa.Text(), nullable=False),
        sa.Column("additional_instruction", sa.Text(), nullable=True),
        sa.Column("document_type", sa.String(length=32), nullable=False),
        sa.Column("detail_level", sa.String(length=16), nullable=False),
        sa.Column("target_audience", sa.String(length=32), nullable=False),
        sa.Column("theme_slug", sa.String(length=32), nullable=False),
        sa.Column("density", sa.String(length=16), nullable=False),
        sa.Column("base_viewer_revision", sa.Integer(), nullable=True),
        sa.Column("commit_sha", sa.String(length=64), nullable=False),
        sa.Column("codex_thread_id", sa.String(length=255), nullable=True),
        sa.Column("codex_turn_id", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("error_retryable", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "operation IN ('create', 'regenerate')", name="ck_generation_jobs_operation"
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_generation_jobs_status",
        ),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["viewer_id"], ["viewers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["retry_of_job_id"], ["generation_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "repository_id", "idempotency_key", name="uq_generation_job_idempotency"
        ),
    )
    op.create_index(
        "uq_generation_jobs_active_repository",
        "generation_jobs",
        ["repository_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
        sqlite_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_index(
        "ix_generation_jobs_repository_created",
        "generation_jobs",
        ["repository_id", "created_at"],
    )
    op.create_index(
        "ix_generation_jobs_status_updated", "generation_jobs", ["status", "updated_at"]
    )
    op.create_index(
        "ix_generation_jobs_viewer_created",
        "generation_jobs",
        ["viewer_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_generation_jobs_viewer_created", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_status_updated", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_repository_created", table_name="generation_jobs")
    op.drop_index("uq_generation_jobs_active_repository", table_name="generation_jobs")
    op.drop_table("generation_jobs")
    op.drop_index("ix_viewers_repository_updated", table_name="viewers")
    op.drop_table("viewers")
