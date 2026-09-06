import asyncio
from pathlib import Path

import pytest

from backend.app.codex import CodexAppServer, CodexConnectionError
from backend.app.settings import Settings

FAKE_SERVER = Path(__file__).parents[1] / "fixtures" / "fake_app_server.py"


def make_settings() -> Settings:
    return Settings(
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
