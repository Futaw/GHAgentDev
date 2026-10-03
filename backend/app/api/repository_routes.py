from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, Response, status

from backend.app.api.repository_schemas import (
    RepositoryCreateRequest,
    RepositoryListResponse,
    RepositoryResponse,
)
from backend.app.repositories import RepositoryService

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


def _service(request: Request) -> RepositoryService:
    return request.app.state.repository_service


@router.get("", response_model=RepositoryListResponse)
async def list_repositories(request: Request) -> RepositoryListResponse:
    return RepositoryListResponse(
        items=[RepositoryResponse.from_model(item) for item in await _service(request).list()]
    )


@router.post("", response_model=RepositoryResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_repository(
    request: Request,
    response: Response,
    payload: RepositoryCreateRequest,
) -> RepositoryResponse:
    repository = await _service(request).create(payload.github_url)
    response.headers["Location"] = f"/api/repositories/{repository.id}"
    response.headers["Retry-After"] = "2"
    return RepositoryResponse.from_model(repository)


@router.get("/{repository_id}", response_model=RepositoryResponse)
async def get_repository(request: Request, repository_id: UUID) -> RepositoryResponse:
    return RepositoryResponse.from_model(await _service(request).get(repository_id))


@router.post(
    "/{repository_id}/sync",
    response_model=RepositoryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def sync_repository(
    request: Request,
    response: Response,
    repository_id: UUID,
) -> RepositoryResponse:
    repository = await _service(request).start_sync(repository_id)
    response.headers["Location"] = f"/api/repositories/{repository.id}"
    response.headers["Retry-After"] = "2"
    return RepositoryResponse.from_model(repository)
