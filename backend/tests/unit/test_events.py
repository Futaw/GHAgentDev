import pytest

from backend.app.events import EventBuffer, encode_sse


@pytest.mark.asyncio
async def test_event_buffer_replays_only_newer_events() -> None:
    events = EventBuffer(max_size=3)
    await events.publish("message.delta", {"delta": "a"})
    second = await events.publish("message.delta", {"delta": "b"})

    replay = await events.wait_after(1, wait_seconds=0.01)

    assert replay == [second]
    assert "id: 2" in encode_sse(second)
    assert "event: message.delta" in encode_sse(second)


@pytest.mark.asyncio
async def test_event_buffer_is_bounded() -> None:
    events = EventBuffer(max_size=2)
    await events.publish("one", {})
    await events.publish("two", {})
    await events.publish("three", {})

    replay = await events.wait_after(0, wait_seconds=0.01)
    assert [event.sequence for event in replay] == [2, 3]
