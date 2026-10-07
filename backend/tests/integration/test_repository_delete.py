from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.main import create_app
from backend.app.repositories.models import Base, RepositoryModel, RepositoryStatus
from backend.app.settings import Settings
from backend.tests.integration.test_repository_api import StubCodex


def make_repository(status: RepositoryStatus = RepositoryStatus.READY) -> RepositoryModel:
    repository_id = uuid4()
    now = datetime.now(UTC)
    return RepositoryModel(
        id=repository_id,
        owner="Example",
        name=f"repo-{repository_id.hex[:8]}",
        canonical_github_url=f"https://github.com/example/{repository_id.hex}",
        workspace_key=str(repository_id),
        status=status.value,
        created_at=now,
        updated_at=now,
    )


async def repository_exists(client: httpx.AsyncClient, repository_id: UUID) -> bool:
    return (await client.get(f"/api/repositories/{repository_id}")).status_code == 200


@pytest.mark.asyncio
async def test_repository_delete_safety_failures_and_retry(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'delete.db'}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    config = Settings(
        database_url=database_url,
        workspace_root=tmp_path / "workspaces",
        test_chat_workspace=tmp_path,
        git_executable="/usr/bin/false",
    )
    app = create_app(config, StubCodex())  # type: ignore[arg-type]

    async with app.router.lifespan_context(app):
        service = app.state.repository_service
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            ready = make_repository()
            await service.store.create(ready)
            ready_path = service.workspace.repository_path(ready.workspace_key)
            (ready_path / ".git").mkdir(parents=True)
            deleted = await client.delete(
                f"/api/repositories/{ready.id}", headers={"X-Trace-ID": "delete-ready"}
            )
            assert deleted.status_code == 204
            assert not ready_path.exists()
            assert not await repository_exists(client, ready.id)

            busy = make_repository(RepositoryStatus.CLONING)
            await service.store.create(busy)
            busy_response = await client.delete(f"/api/repositories/{busy.id}")
            assert busy_response.status_code == 409
            assert busy_response.json()["code"] == "REPOSITORY_BUSY"
            assert await repository_exists(client, busy.id)

            in_use = make_repository()
            await service.store.create(in_use)
            original_related = service.store.has_related_data
            service.store.has_related_data = AsyncMock(return_value=True)
            in_use_response = await client.delete(f"/api/repositories/{in_use.id}")
            assert in_use_response.status_code == 409
            assert in_use_response.json()["code"] == "REPOSITORY_IN_USE"
            assert await repository_exists(client, in_use.id)
            service.store.has_related_data = original_related

            unsafe = make_repository()
            await service.store.create(unsafe)
            outside = tmp_path / "outside"
            outside.mkdir()
            service.workspace.repositories_root.joinpath(unsafe.workspace_key).symlink_to(
                outside, target_is_directory=True
            )
            unsafe_response = await client.delete(f"/api/repositories/{unsafe.id}")
            assert unsafe_response.status_code == 500
            assert unsafe_response.json()["code"] == "DELETE_FAILED"
            assert str(tmp_path) not in unsafe_response.json()["detail"]
            assert await repository_exists(client, unsafe.id)
            assert outside.is_dir()

            retryable = make_repository()
            await service.store.create(retryable)
            retryable_path = service.workspace.repository_path(retryable.workspace_key)
            retryable_path.mkdir()
            original_delete = service.store.delete
            service.store.delete = AsyncMock(side_effect=SQLAlchemyError())
            database_failure = await client.delete(f"/api/repositories/{retryable.id}")
            assert database_failure.status_code == 503
            assert database_failure.json()["code"] == "DATABASE_UNAVAILABLE"
            assert not retryable_path.exists()
            assert await repository_exists(client, retryable.id)

            service.store.delete = original_delete
            retry = await client.delete(f"/api/repositories/{retryable.id}")
            assert retry.status_code == 204
            assert not await repository_exists(client, retryable.id)
