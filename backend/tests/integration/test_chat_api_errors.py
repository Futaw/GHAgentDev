import logging
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.codex import CodexConnectionError, CodexTimeoutError
from backend.app.main import create_app
from backend.app.repositories.models import Base
from backend.app.settings import Settings


class FailingCodex:
    connected = True
    last_error = None

    def __init__(self, error: Exception) -> None:
        self.error = error

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    def add_notification_handler(self, _handler) -> None:  # type: ignore[no-untyped-def]
        pass

    async def ensure_connected(self) -> None:
        if isinstance(self.error, CodexConnectionError):
            raise self.error

    async def request(self, _method: str, _params: dict) -> dict:  # type: ignore[type-arg]
        raise self.error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status", "code", "classification"),
    [
        (
            CodexConnectionError("Codex App Server is unavailable"),
            503,
            "CODEX_UNAVAILABLE",
            "unavailable",
        ),
        (CodexTimeoutError("thread/start"), 504, "CODEX_TIMEOUT", "timeout"),
    ],
)
async def test_session_creation_returns_safe_problem_details_and_does_not_leak_session(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    status: int,
    code: str,
    classification: str,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'chat-errors.db'}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()

    test_workspace = tmp_path / "private-workspace"
    test_workspace.mkdir()
    config = Settings(
        database_url=database_url,
        workspace_root=tmp_path / "workspaces",
        test_chat_workspace=test_workspace,
    )
    app = create_app(config, FailingCodex(error))  # type: ignore[arg-type]
    caplog.set_level(logging.WARNING, logger="backend.app.main")

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/chat/sessions",
                headers={"X-Trace-ID": "trace-test"},
            )

    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == code
    assert body["trace_id"] == "trace-test"
    assert str(tmp_path) not in body["detail"]
    assert app.state.chat_service._sessions == {}
    record = next(item for item in caplog.records if getattr(item, "problem_code", None) == code)
    assert record.operation == "chat.session.create"
    assert record.trace_id == "trace-test"
    assert record.classification == classification
    assert str(tmp_path) not in record.getMessage()
