import asyncio
from pathlib import Path

import pytest

from backend.app.codex import CodexAppServer, CodexConnectionError, CodexTimeoutError
from backend.app.settings import Settings

FAKE_SERVER = Path(__file__).parents[1] / "fixtures" / "fake_app_server.py"


def make_settings() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        codex_executable=str(FAKE_SERVER),
        test_chat_workspace=Path.cwd(),
        codex_request_timeout_seconds=2,
        codex_restart_delay_seconds=0.05,
        sse_heartbeat_seconds=0.05,
    )


@pytest.mark.asyncio
async def test_handshake_requests_and_notifications() -> None:
    client = CodexAppServer(make_settings())
    received: list[tuple[str, dict]] = []

    async def collect(method: str, params: dict) -> None:
        received.append((method, params))

    client.add_notification_handler(collect)
    await client.start()
    try:
        account = await client.request("account/read", {"refreshToken": False})
        thread = await client.request("thread/start", {})
        await client.request(
            "turn/start",
            {"threadId": thread["thread"]["id"], "input": [{"type": "text", "text": "hello"}]},
        )
        for _ in range(20):
            if any(method == "turn/completed" for method, _ in received):
                break
            await asyncio.sleep(0.01)

        assert client.connected is True
        assert account["account"]["planType"] == "plus"
        assert (
            "item/agentMessage/delta",
            {
                "threadId": "thr_test",
                "turnId": "turn_test",
                "itemId": "item_test",
                "delta": "fake answer",
            },
        ) in received
        assert any(method == "turn/completed" for method, _ in received)
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_restarts_and_reinitializes_after_process_exit() -> None:
    client = CodexAppServer(make_settings())
    await client.start()
    first_pid = client._process.pid  # process identity is the behavior under test
    try:
        with pytest.raises(CodexConnectionError):
            await client.request("test/crash", {})
        for _ in range(100):
            if client.connected and client._process and client._process.pid != first_pid:
                break
            await asyncio.sleep(0.02)
        assert client.connected is True
        assert client._process is not None
        assert client._process.pid != first_pid
        assert (await client.request("account/read"))["account"]["type"] == "chatgpt"
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_request_timeout_is_distinct_from_connection_failure() -> None:
    settings = make_settings()
    client = CodexAppServer(settings)
    await client.start()
    try:
        settings.codex_request_timeout_seconds = 0.01
        with pytest.raises(CodexTimeoutError) as captured:
            await client.request("test/hang", {})
        assert captured.value.method == "test/hang"
        assert client.connected is True
    finally:
        await client.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind, expected",
    [
        ("commandExecution", {"decision": "decline"}),
        ("fileChange", {"decision": "decline"}),
        ("permissions", {"permissions": {}, "scope": "turn"}),
    ],
)
async def test_rejects_schema_shaped_approval_and_reader_keeps_running(kind, expected):
    client = CodexAppServer(make_settings())
    await client.start()
    try:
        response = await client.request("test/approval", {"kind": kind})
        assert response["result"] == expected
        assert client.rejection_count == 1
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_notification_handler_can_request_without_blocking_reader():
    client = CodexAppServer(make_settings())
    finished = asyncio.Event()

    async def handler(method, params):
        if method == "turn/completed":
            await client.request("account/read", {})
            finished.set()

    client.add_notification_handler(handler)
    await client.start()
    try:
        await client.request("turn/start", {})
        await asyncio.wait_for(finished.wait(), 1)
    finally:
        await client.stop()
