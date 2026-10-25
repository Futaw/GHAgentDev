from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.repositories.models import Base, RepositoryModel
from backend.app.settings import Settings


class StructuredCodex:
    connected = True
    last_error = None

    def __init__(self, document: dict[str, object]) -> None:
        self.document = document
        self.handlers = []
        self.thread_params: dict[str, object] | None = None
        self.turn_params: dict[str, object] | None = None

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    def add_notification_handler(self, handler) -> None:  # type: ignore[no-untyped-def]
        self.handlers.append(handler)

    async def request(self, method: str, params: dict[str, object]):
        if method == "config/read":
            return {
                "config": {
                    "sandbox_mode": None,
                    "sandbox_workspace_write": None,
                    "apps": None,
                    "mcp_servers": {"external": {"enabled": True}},
                }
            }
        if method == "configRequirements/read":
            return {"requirements": None}
        if method == "plugin/list":
            return {"data": []}
        if method == "thread/start":
            self.thread_params = params
            return {"thread": {"id": "thread-generation"}}
        if method == "turn/start":
            self.turn_params = params
            asyncio.create_task(self._complete())
            return {"turn": {"id": "turn-generation", "status": "inProgress"}}
        if method == "turn/interrupt":
            return {}
        return {}

    async def _complete(self) -> None:
        await asyncio.sleep(0)
        messages = [
            (
                "item/agentMessage/delta",
                {
                    "threadId": "thread-generation",
                    "turnId": "turn-generation",
                    "delta": json.dumps(self.document, ensure_ascii=False),
                },
            ),
            (
                "turn/completed",
                {
                    "threadId": "thread-generation",
                    "turn": {"id": "turn-generation", "status": "completed"},
                },
            ),
        ]
        for method, params in messages:
            await asyncio.gather(*(handler(method, params) for handler in self.handlers))


async def git(path: Path, *arguments: str) -> str:
    process = await asyncio.create_subprocess_exec(
        "git", "-C", str(path), *arguments, stdout=asyncio.subprocess.PIPE
    )
    stdout, _ = await process.communicate()
    assert process.returncode == 0
    return stdout.decode().strip()


@pytest.mark.asyncio
async def test_generation_api_saves_only_validated_viewer(tmp_path: Path) -> None:
    from backend.app.main import create_app

    repository_id = uuid4()
    workspace_root = tmp_path / "workspaces"
    repository = workspace_root / "repositories" / str(repository_id)
    repository.mkdir(parents=True)
    await git(repository, "init")
    await git(repository, "config", "user.email", "test@example.com")
    await git(repository, "config", "user.name", "Test")
    (repository / "main.py").write_text("print('fixture')\n")
    await git(repository, "add", "main.py")
    await git(repository, "commit", "-m", "fixture")
    commit = await git(repository, "rev-parse", "HEAD")
    document = {
        "schema_version": "1.0",
        "title": "Fixture Viewer",
        "summary": "Fixture repository viewer.",
        "sections": [
            {
                "id": "overview",
                "heading": "Overview",
                "summary": None,
                "blocks": [
                    {
                        "id": "description",
                        "type": "paragraph",
                        "title": None,
                        "source_reference_ids": ["source-main"],
                        "text": "The fixture prints one line.",
                    }
                ],
            }
        ],
        "source_references": [
            {
                "id": "source-main",
                "path": "main.py",
                "start_line": 1,
                "end_line": 1,
                "description": "Fixture source",
            }
        ],
        "limitations": [],
    }
    codex = StructuredCodex(document)
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'generation.db'}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with sessions() as session:
        session.add(
            RepositoryModel(
                id=repository_id,
                owner="example",
                name="repo",
                canonical_github_url="https://github.com/example/repo",
                workspace_key=str(repository_id),
                default_branch="main",
                latest_commit_sha=commit,
                status="ready",
                last_synced_at=now,
                last_error_code=None,
                last_error_message=None,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
    await engine.dispose()
    settings = Settings(
        database_url=database_url,
        workspace_root=workspace_root,
        test_chat_workspace=tmp_path,
        generation_enabled=True,
    )
    app = create_app(settings, codex)  # type: ignore[arg-type]
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "request": "Explain the fixture",
                "document_type": "functional_spec",
                "detail_level": "standard",
                "target_audience": "engineer",
                "theme_slug": "technical-light",
                "density": "comfortable",
                "additional_instruction": None,
            }
            created = await client.post(
                f"/api/repositories/{repository_id}/viewers",
                headers={"Idempotency-Key": "a" * 32},
                json=payload,
            )
            assert created.status_code == 202
            job_id = created.json()["id"]
            for _ in range(100):
                detail = await client.get(f"/api/generation-jobs/{job_id}")
                if detail.json()["status"] not in {"queued", "running"}:
                    break
                await asyncio.sleep(0.02)
            assert detail.json()["status"] == "completed", detail.json()
            viewer_id = detail.json()["viewer_id"]
            viewer = await client.get(f"/api/viewers/{viewer_id}")
            assert viewer.status_code == 200
            assert viewer.json()["content_json"]["title"] == "Fixture Viewer"
            assert "data-source-reference-id" in viewer.json()["sanitized_html"]
            assert codex.thread_params is not None
            assert "sandboxPolicy" not in codex.thread_params
            profile = codex.thread_params["config"]
            assert profile["web_search"] == "disabled"  # type: ignore[index]
            assert profile["mcp_servers"]["external"]["enabled"] is False  # type: ignore[index]
            assert codex.turn_params is not None
            assert codex.turn_params["disabledPluginIds"] == []
            assert "outputSchema" in codex.turn_params

            same = await client.post(
                f"/api/repositories/{repository_id}/viewers",
                headers={"Idempotency-Key": "a" * 32},
                json=payload,
            )
            assert same.json()["id"] == job_id

            before_html = viewer.json()["sanitized_html"]
            appearance = await client.patch(
                f"/api/viewers/{viewer_id}/appearance",
                json={"theme_slug": "editorial", "density": "compact"},
            )
            assert appearance.status_code == 200
            updated = await client.get(f"/api/viewers/{viewer_id}")
            assert updated.json()["sanitized_html"] == before_html
            assert updated.json()["theme_slug"] == "editorial"
            assert updated.json()["content_revision"] == 1

            in_use = await client.delete(f"/api/repositories/{repository_id}")
            assert in_use.status_code == 409
            assert in_use.json()["code"] == "REPOSITORY_IN_USE"
            deleted_viewer = await client.delete(f"/api/viewers/{viewer_id}")
            assert deleted_viewer.status_code == 204
            deleted_repository = await client.delete(f"/api/repositories/{repository_id}")
            assert deleted_repository.status_code == 204
            deleted_job = await client.get(f"/api/generation-jobs/{job_id}")
            assert deleted_job.status_code == 404


@pytest.mark.asyncio
async def test_generation_is_disabled_by_default(tmp_path: Path) -> None:
    from backend.app.main import create_app

    database_url = f"sqlite+aiosqlite:///{tmp_path / 'disabled.db'}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    app = create_app(
        Settings(
            database_url=database_url, workspace_root=tmp_path / "ws", test_chat_workspace=tmp_path
        ),
        StructuredCodex({}),  # type: ignore[arg-type]
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/repositories/{uuid4()}/viewers",
                headers={"Idempotency-Key": "disabled"},
                json={
                    "request": "x",
                    "document_type": "functional_spec",
                    "detail_level": "standard",
                    "target_audience": "engineer",
                    "theme_slug": "technical-light",
                    "density": "comfortable",
                    "additional_instruction": None,
                },
            )
            assert response.status_code == 503
            assert response.json()["code"] == "GENERATION_DISABLED"
