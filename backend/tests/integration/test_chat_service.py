import asyncio

import pytest

from backend.app.chat import ChatService
from backend.app.codex import CodexAppServer
from backend.tests.integration.test_codex_client import make_settings


@pytest.mark.asyncio
async def test_chat_turn_streams_delta_and_completion() -> None:
    config = make_settings()
    client = CodexAppServer(config)
    service = ChatService(client, config)
    await client.start()
    try:
        session = await service.create_session()
        turn = await service.send_message(session.id, "Say hello")
        events = []
        sequence = 0
        for _ in range(20):
            batch = await turn.events.wait_after(sequence, 0.1)
            events.extend(batch)
            if batch:
                sequence = batch[-1].sequence
            if any(event.event_type == "turn.completed" for event in events):
                break
            await asyncio.sleep(0)

        assert [event.event_type for event in events] == [
            "turn.started",
            "message.delta",
            "turn.completed",
        ]
        assert session.messages[-1].content == "fake answer"
        assert turn.status == "completed"
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_chat_recreates_ephemeral_thread_after_disconnect() -> None:
    config = make_settings()
    client = CodexAppServer(config)
    service = ChatService(client, config)
    await client.start()
    try:
        session = await service.create_session()
        assert session.codex_thread_id == "thr_test"

        await service._handle_notification("app_server/disconnected", {})
        assert session.codex_thread_id is None

        turn = await service.send_message(session.id, "Try again")
        for _ in range(20):
            if turn.status == "completed":
                break
            await asyncio.sleep(0.01)
        assert session.codex_thread_id == "thr_test"
        assert turn.status == "completed"
    finally:
        await client.stop()
