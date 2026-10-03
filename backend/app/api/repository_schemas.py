from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from backend.app.repositories.models import RepositoryModel


class RepositoryCreateRequest(BaseModel):
    github_url: str


class RepositoryErrorResponse(BaseModel):
    code: str
    message: str
    retryable: bool = True


class RepositoryResponse(BaseModel):
    id: UUID
    owner: str
    name: str
    full_name: str
    github_url: str
    default_branch: str | None
    latest_commit_sha: str | None
    status: Literal["pending", "cloning", "ready", "syncing", "failed"]
    last_synced_at: datetime | None
    last_error: RepositoryErrorResponse | None
    viewer_count: int = 0
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: RepositoryModel) -> RepositoryResponse:
        error = None
        if model.last_error_code and model.last_error_message:
            error = RepositoryErrorResponse(
                code=model.last_error_code,
                message=model.last_error_message,
            )
        return cls(
            id=model.id,
            owner=model.owner,
            name=model.name,
            full_name=f"{model.owner}/{model.name}",
            github_url=model.canonical_github_url,
            default_branch=model.default_branch,
            latest_commit_sha=model.latest_commit_sha,
            status=model.status,
            last_synced_at=model.last_synced_at,
            last_error=error,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class RepositoryListResponse(BaseModel):
    items: list[RepositoryResponse]
