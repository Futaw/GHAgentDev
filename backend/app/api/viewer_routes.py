from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response, status
from fastapi.responses import StreamingResponse

from backend.app.api.routes import _event_id, _event_stream
from backend.app.api.viewer_schemas import (
    AppearanceRequest,
    GenerationJobResponse,
    ViewerCreateRequest,
    ViewerListResponse,
    ViewerResponse,
    ViewerSummaryResponse,
)
from backend.app.generation.service import GenerationService
from backend.app.viewers.options import viewer_options

router = APIRouter(prefix="/api", tags=["viewers"])


def _service(request: Request) -> GenerationService:
    return request.app.state.generation_service


@router.get("/viewer-options")
async def options() -> dict[str, object]:
    return viewer_options()


@router.get(
    "/repositories/{repository_id}/viewers",
    response_model=ViewerListResponse,
)
async def list_viewers(request: Request, repository_id: UUID) -> ViewerListResponse:
    return ViewerListResponse(
        items=[
            ViewerSummaryResponse.from_model(item)
            for item in await _service(request).list_viewers(repository_id)
        ]
    )


@router.post(
    "/repositories/{repository_id}/viewers",
    response_model=GenerationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_viewer(
    request: Request,
    response: Response,
    repository_id: UUID,
    payload: ViewerCreateRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> GenerationJobResponse:
    job = await _service(request).create(repository_id, idempotency_key, payload.model_dump())
    response.headers["Location"] = f"/api/generation-jobs/{job.id}"
    response.headers["Retry-After"] = "2"
    return GenerationJobResponse.from_model(job)


@router.get("/viewers/{viewer_id}", response_model=ViewerResponse)
async def get_viewer(request: Request, viewer_id: UUID) -> ViewerResponse:
    service = _service(request)
    viewer = await service.get_viewer(viewer_id)
    repository = await service.repositories.get(viewer.repository_id)
    return ViewerResponse(
        **ViewerSummaryResponse.from_model(viewer).model_dump(),
        content_json=viewer.content_json,
        sanitized_html=viewer.sanitized_html,
        renderer_version=viewer.renderer_version,
        repository={
            "id": repository.id,
            "full_name": f"{repository.owner}/{repository.name}",
            "github_url": repository.canonical_github_url,
            "default_branch": repository.default_branch,
        },
    )


@router.post(
    "/viewers/{viewer_id}/regenerate",
    response_model=GenerationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def regenerate_viewer(
    request: Request,
    response: Response,
    viewer_id: UUID,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> GenerationJobResponse:
    job = await _service(request).regenerate(viewer_id, idempotency_key)
    response.headers["Location"] = f"/api/generation-jobs/{job.id}"
    response.headers["Retry-After"] = "2"
    return GenerationJobResponse.from_model(job)


@router.patch("/viewers/{viewer_id}/appearance", response_model=ViewerSummaryResponse)
async def update_viewer_appearance(
    request: Request, viewer_id: UUID, payload: AppearanceRequest
) -> ViewerSummaryResponse:
    viewer = await _service(request).update_appearance(
        viewer_id, payload.theme_slug, payload.density
    )
    return ViewerSummaryResponse.from_model(viewer)


@router.delete("/viewers/{viewer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_viewer(request: Request, viewer_id: UUID) -> Response:
    await _service(request).delete(viewer_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/generation-jobs/{job_id}", response_model=GenerationJobResponse)
async def get_generation_job(request: Request, job_id: UUID) -> GenerationJobResponse:
    return GenerationJobResponse.from_model(await _service(request).get_job(job_id))


@router.get("/generation-jobs/{job_id}/events")
async def generation_job_events(
    request: Request,
    job_id: UUID,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    await _service(request).get_job(job_id)
    return StreamingResponse(
        _event_stream(
            request,
            _service(request).runner.event_buffer(job_id),
            request.app.state.settings.sse_heartbeat_seconds,
            _event_id(last_event_id),
            {"job.completed", "job.failed", "job.cancelled"},
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/generation-jobs/{job_id}/cancel", response_model=GenerationJobResponse)
async def cancel_generation_job(
    request: Request, response: Response, job_id: UUID
) -> GenerationJobResponse:
    job = await _service(request).cancel(job_id)
    response.status_code = 200 if job.status in {"completed", "failed", "cancelled"} else 202
    return GenerationJobResponse.from_model(job)


@router.post(
    "/generation-jobs/{job_id}/retry",
    response_model=GenerationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_generation_job(
    request: Request,
    response: Response,
    job_id: UUID,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> GenerationJobResponse:
    job = await _service(request).retry(job_id, idempotency_key)
    response.headers["Location"] = f"/api/generation-jobs/{job.id}"
    return GenerationJobResponse.from_model(job)
