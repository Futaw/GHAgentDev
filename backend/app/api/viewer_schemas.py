from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.generation.models import GenerationJobModel, ViewerModel


class ViewerCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: str = Field(min_length=1, max_length=4000)
    document_type: Literal["functional_spec", "technical_guide", "process_flow"]
    detail_level: Literal["overview", "standard", "detailed"]
    target_audience: Literal["engineer", "beginner", "product_manager"]
    theme_slug: Literal["technical-light", "editorial"]
    density: Literal["comfortable", "compact"]
    additional_instruction: str | None = Field(default=None, max_length=4000)

    @field_validator("request")
    @classmethod
    def non_empty_request(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("request is required")
        return value

    @field_validator("additional_instruction")
    @classmethod
    def normalize_additional(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None


class AppearanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    theme_slug: Literal["technical-light", "editorial"] | None = None
    density: Literal["comfortable", "compact"] | None = None

    @model_validator(mode="after")
    def one_value(self) -> AppearanceRequest:
        if self.theme_slug is None and self.density is None:
            raise ValueError("theme_slug or density is required")
        return self


class ViewerSummaryResponse(BaseModel):
    id: UUID
    repository_id: UUID
    title: str
    summary: str
    document_type: str
    detail_level: str
    target_audience: str
    theme_slug: str
    density: str
    commit_sha: str
    content_revision: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: ViewerModel) -> ViewerSummaryResponse:
        return cls.model_validate(model, from_attributes=True)


class ViewerResponse(ViewerSummaryResponse):
    content_json: dict[str, object]
    sanitized_html: str
    renderer_version: str
    repository: dict[str, object]


class ViewerListResponse(BaseModel):
    items: list[ViewerSummaryResponse]


class GenerationJobResponse(BaseModel):
    id: UUID
    repository_id: UUID
    viewer_id: UUID | None
    retry_of_job_id: UUID | None
    operation: str
    status: str
    current_phase: str
    started_at: datetime | None
    completed_at: datetime | None
    error: dict[str, object] | None
    created_at: datetime
    updated_at: datetime
    events_url: str

    @classmethod
    def from_model(cls, model: GenerationJobModel) -> GenerationJobResponse:
        error = None
        if model.error_code:
            error = {
                "code": model.error_code,
                "message": model.error_message,
                "retryable": bool(model.error_retryable),
            }
        return cls(
            id=model.id,
            repository_id=model.repository_id,
            viewer_id=model.viewer_id,
            retry_of_job_id=model.retry_of_job_id,
            operation=model.operation,
            status=model.status,
            current_phase=model.current_phase,
            started_at=model.started_at,
            completed_at=model.completed_at,
            error=error,
            created_at=model.created_at,
            updated_at=model.updated_at,
            events_url=f"/api/generation-jobs/{model.id}/events",
        )
