from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.orm import Base


class GenerationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GenerationOperation(StrEnum):
    CREATE = "create"
    REGENERATE = "regenerate"


class ViewerModel(Base):
    __tablename__ = "viewers"
    __table_args__ = (
        Index("ix_viewers_repository_updated", "repository_id", "updated_at"),
        CheckConstraint("content_revision >= 1", name="ck_viewers_content_revision"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    repository_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(String(1000))
    document_type: Mapped[str] = mapped_column(String(32))
    detail_level: Mapped[str] = mapped_column(String(16))
    target_audience: Mapped[str] = mapped_column(String(32))
    theme_slug: Mapped[str] = mapped_column(String(32))
    density: Mapped[str] = mapped_column(String(16))
    content_json: Mapped[dict[str, object]] = mapped_column(JSON)
    sanitized_html: Mapped[str] = mapped_column(Text)
    request: Mapped[str] = mapped_column(Text)
    additional_instruction: Mapped[str | None] = mapped_column(Text)
    commit_sha: Mapped[str] = mapped_column(String(64))
    renderer_version: Mapped[str] = mapped_column(String(32))
    content_revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GenerationJobModel(Base):
    __tablename__ = "generation_jobs"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('create', 'regenerate')", name="ck_generation_jobs_operation"
        ),
        UniqueConstraint("repository_id", "idempotency_key", name="uq_generation_job_idempotency"),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_generation_jobs_status",
        ),
        Index(
            "uq_generation_jobs_active_repository",
            "repository_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
        Index("ix_generation_jobs_repository_created", "repository_id", "created_at"),
        Index("ix_generation_jobs_status_updated", "status", "updated_at"),
        Index("ix_generation_jobs_viewer_created", "viewer_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    repository_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id", ondelete="RESTRICT"), nullable=False
    )
    viewer_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("viewers.id", ondelete="SET NULL")
    )
    retry_of_job_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("generation_jobs.id", ondelete="SET NULL")
    )
    operation: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    current_phase: Mapped[str] = mapped_column(String(32))
    request: Mapped[str] = mapped_column(Text)
    additional_instruction: Mapped[str | None] = mapped_column(Text)
    document_type: Mapped[str] = mapped_column(String(32))
    detail_level: Mapped[str] = mapped_column(String(16))
    target_audience: Mapped[str] = mapped_column(String(32))
    theme_slug: Mapped[str] = mapped_column(String(32))
    density: Mapped[str] = mapped_column(String(16))
    base_viewer_revision: Mapped[int | None] = mapped_column(Integer)
    commit_sha: Mapped[str] = mapped_column(String(64))
    codex_thread_id: Mapped[str | None] = mapped_column(String(255))
    codex_turn_id: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    error_retryable: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
