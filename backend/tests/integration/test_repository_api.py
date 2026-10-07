import asyncio
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.main import create_app
from backend.app.repositories.models import Base
from backend.app.settings import Settings


class StubCodex:
    connected = True
    last_error = None

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    def add_notification_handler(self, _handler) -> None:  # type: ignore[no-untyped-def]
        pass


@pytest.mark.asyncio
async def test_repository_api_contract_and_async_failure(tmp_path: Path) -> None:
    database_path = tmp_path / "api.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()

    config = Settings(
        database_url=database_url,
        workspace_root=tmp_path / "workspaces",
        test_chat_workspace=tmp_path,
        git_executable="/usr/bin/false",
        git_clone_timeout_seconds=1,
        git_sync_timeout_seconds=1,
    )
    app = create_app(config, StubCodex())  # type: ignore[arg-type]
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            invalid = await client.post(
                "/api/repositories", json={"github_url": "file:///tmp/repository"}
            )
            assert invalid.status_code == 422
            assert invalid.json()["code"] == "INVALID_GITHUB_URL"
            blank = await client.post("/api/repositories", json={"github_url": "   "})
            assert blank.status_code == 422
            assert blank.json()["code"] == "INVALID_GITHUB_URL"

            created = await client.post(
                "/api/repositories",
                json={"github_url": "https://github.com/Futaw/GHAgentDev.git"},
            )
            assert created.status_code == 202
            repository_id = created.json()["id"]
            assert created.headers["location"] == f"/api/repositories/{repository_id}"
            assert created.headers["retry-after"] == "2"
            assert "workspace_key" not in created.json()

            duplicate = await client.post(
                "/api/repositories",
                json={"github_url": "https://github.com/futaw/ghagentdev"},
            )
            assert duplicate.status_code == 409
            assert duplicate.json()["code"] == "REPOSITORY_ALREADY_REGISTERED"
            assert duplicate.json()["repository_id"] == repository_id

            for _ in range(50):
                detail = await client.get(f"/api/repositories/{repository_id}")
                if detail.json()["status"] == "failed":
                    break
                await asyncio.sleep(0.01)
            body = detail.json()
            assert body["status"] == "failed"
            assert body["last_error"]["code"] == "CLONE_FAILED"
            assert str(tmp_path) not in body["last_error"]["message"]

            listing = await client.get("/api/repositories")
            assert listing.status_code == 200
            assert [item["id"] for item in listing.json()["items"]] == [repository_id]

            missing = await client.get(f"/api/repositories/{uuid4()}")
            assert missing.status_code == 404
            assert missing.json()["code"] == "REPOSITORY_NOT_FOUND"

            invalid_id = await client.get("/api/repositories/not-a-uuid")
            assert invalid_id.status_code == 422
            assert invalid_id.json()["code"] == "VALIDATION_ERROR"

            deleted = await client.delete(f"/api/repositories/{repository_id}")
            assert deleted.status_code == 204
            deleted_detail = await client.get(f"/api/repositories/{repository_id}")
            assert deleted_detail.status_code == 404

            recreated = await client.post(
                "/api/repositories",
                json={"github_url": "https://github.com/Futaw/GHAgentDev"},
            )
            assert recreated.status_code == 202
