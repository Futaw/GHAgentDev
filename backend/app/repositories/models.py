from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RepositoryStatus(StrEnum):
    PENDING = "pending"
    CLONING = "cloning"
    READY = "ready"
    SYNCING = "syncing"
    FAILED = "failed"


class RepositoryModel(Base):
    __tablename__ = "repositories"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'cloning', 'ready', 'syncing', 'failed')",
            name="ck_repositories_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner: Mapped[str] = mapped_column(String(39))
    name: Mapped[str] = mapped_column(String(100))
    canonical_github_url: Mapped[str] = mapped_column(String(255), unique=True)
    workspace_key: Mapped[str] = mapped_column(String(36), unique=True)
    default_branch: Mapped[str | None] = mapped_column(String(255))
    latest_commit_sha: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
