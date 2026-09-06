from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class StreamEvent:
    sequence: int
    event_type: str
    payload: dict[str, Any]
    occurred_at: str


class EventBuffer:
    def __init__(self, max_size: int) -> None:
        self._events: deque[StreamEvent] = deque(maxlen=max_size)
        self._sequence = 0
        self._condition = asyncio.Condition()

    async def publish(self, event_type: str, payload: dict[str, Any]) -> StreamEvent:
        async with self._condition:
            self._sequence += 1
            event = StreamEvent(
                sequence=self._sequence,
                event_type=event_type,
                payload=payload,
                occurred_at=datetime.now(UTC).isoformat(),
            )
            self._events.append(event)
            self._condition.notify_all()
            return event

    async def wait_after(self, sequence: int, wait_seconds: float) -> list[StreamEvent]:
        async with self._condition:
            events = [event for event in self._events if event.sequence > sequence]
            if events:
                return events
            try:
                await asyncio.wait_for(self._condition.wait(), timeout=wait_seconds)
            except TimeoutError:
                return []
            return [event for event in self._events if event.sequence > sequence]


def encode_sse(event: StreamEvent) -> str:
    import json

    data = {
        **event.payload,
        "sequence": event.sequence,
        "occurred_at": event.occurred_at,
    }
    return (
        f"id: {event.sequence}\n"
        f"event: {event.event_type}\n"
        f"data: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )
