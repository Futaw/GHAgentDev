import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from backend.app.generation.runner import GenerationRunError, GenerationRunner, TurnCapture
from backend.app.generation.security import GenerationSecurityError


@pytest.mark.parametrize(
    "status,requested,expected",
    [
        ("interrupted", True, asyncio.CancelledError),
        ("interrupted", False, GenerationRunError),
        ("failed", True, GenerationRunError),
    ],
)
async def test_only_requested_interruption_is_cancellation(status, requested, expected):
    job_id = uuid4()
    store = SimpleNamespace(is_cancel_requested=AsyncMock(return_value=requested))
    codex = SimpleNamespace(
        connected=True, security_epoch=1, request=AsyncMock(), discard_connection=AsyncMock()
    )
    runner = object.__new__(GenerationRunner)
    runner.store = store
    runner.codex = codex
    capture = TurnCapture(
        thread_id="thread",
        job_id=job_id,
        turn_id="turn",
        completed=asyncio.get_running_loop().create_future(),
    )
    runner.captures = {"thread": capture}
    runner.inspections = {job_id: SimpleNamespace(thread_id="thread")}
    await runner._handle_notification(
        "turn/completed",
        {
            "threadId": "thread",
            "turn": {"id": "turn", "status": status, "items": []},
        },
    )
    with pytest.raises(expected):
        await capture.completed
    await runner._stop_job(job_id)
    codex.request.assert_not_awaited()
    codex.discard_connection.assert_not_awaited()
    if status == "interrupted":
        store.is_cancel_requested.assert_awaited_once_with(job_id)
    else:
        store.is_cancel_requested.assert_not_awaited()


async def test_cancel_does_not_hide_unexpected_tool_or_unconfirmed_stop():
    job_id = uuid4()
    codex = SimpleNamespace(
        connected=True, security_epoch=1, request=AsyncMock(), discard_connection=AsyncMock()
    )
    runner = object.__new__(GenerationRunner)
    runner.store = SimpleNamespace(is_cancel_requested=AsyncMock(return_value=True))
    runner.codex = codex
    capture = TurnCapture(
        thread_id="thread",
        job_id=job_id,
        turn_id="turn",
        completed=asyncio.get_running_loop().create_future(),
    )
    runner.captures = {"thread": capture}
    runner.inspections = {job_id: SimpleNamespace(thread_id="thread")}
    await runner._handle_notification(
        "turn/completed",
        {
            "threadId": "thread",
            "turn": {"id": "turn", "status": "interrupted", "items": [{"type": "mcpToolCall"}]},
        },
    )
    with pytest.raises(GenerationSecurityError):
        await capture.completed
    assert capture.terminal_status is None
    await runner._stop_job(job_id)
    codex.request.assert_awaited_once()
    codex.discard_connection.assert_awaited_once()
    runner.store.is_cancel_requested.assert_not_awaited()
