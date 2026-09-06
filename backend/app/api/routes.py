from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Header, Request, Response, status
from fastapi.responses import StreamingResponse

from backend.app.api.models import (
    AuthStatusResponse,
    ChatMessageRequest,
    LoginResponse,
    TurnAcceptedResponse,
)
from backend.app.auth import AuthService
from backend.app.chat import ChatService
from backend.app.events import EventBuffer, encode_sse

router = APIRouter(prefix="/api")


def _auth(request: Request) -> AuthService:
    return request.app.state.auth_service


def _chat(request: Request) -> ChatService:
    return request.app.state.chat_service


def _event_id(value: str | None) -> int:
    if not value:
        return 0
    try:
        return max(0, int(value))
    except ValueError:
        return 0


async def _event_stream(
    request: Request,
    events: EventBuffer,
    heartbeat_seconds: float,
    after_sequence: int,
    terminal_events: set[str] | None = None,
) -> AsyncIterator[str]:
    sequence = after_sequence
    while not await request.is_disconnected():
        batch = await events.wait_after(sequence, heartbeat_seconds)
        if not batch:
            yield "event: heartbeat\ndata: {}\n\n"
            continue
        for event in batch:
            sequence = event.sequence
            yield encode_sse(event)
            if terminal_events and event.event_type in terminal_events:
                return
        await asyncio.sleep(0)


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    codex = request.app.state.codex
    return {
        "status": "ok",
        "http_server": True,
        "app_server_connected": codex.connected,
        "app_server_error": None if codex.connected else codex.last_error,
    }


@router.get("/auth/status", response_model=AuthStatusResponse)
async def auth_status(request: Request) -> dict[str, object]:
    return await _auth(request).status()


@router.post("/auth/login", response_model=LoginResponse)
async def auth_login(request: Request) -> dict[str, object]:
    return await _auth(request).login()


@router.post("/auth/login/{login_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def auth_login_cancel(request: Request, login_id: str) -> Response:
    await _auth(request).cancel(login_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auth/events")
async def auth_events(
    request: Request,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(
            request,
            _auth(request).events,
            request.app.state.settings.sse_heartbeat_seconds,
            _event_id(last_event_id),
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def auth_logout(request: Request) -> Response:
    await _auth(request).logout()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/chat/sessions", status_code=status.HTTP_201_CREATED)
async def create_chat_session(request: Request) -> dict[str, object]:
    session = await _chat(request).create_session()
    return _chat(request).serialize_session(session)


@router.get("/chat/sessions/{session_id}")
async def get_chat_session(request: Request, session_id: str) -> dict[str, object]:
    return _chat(request).serialize_session(_chat(request).get_session(session_id))


@router.get("/chat/sessions/{session_id}/messages")
async def get_chat_messages(request: Request, session_id: str) -> dict[str, object]:
    session = _chat(request).get_session(session_id)
    return {"messages": [_chat(request).serialize_message(item) for item in session.messages]}


@router.post(
    "/chat/sessions/{session_id}/messages",
    response_model=TurnAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_chat_message(
    request: Request,
    session_id: str,
    payload: ChatMessageRequest,
) -> dict[str, str]:
    turn = await _chat(request).send_message(session_id, payload.content)
    return {
        "turn_id": turn.id,
        "status": turn.status,
        "events_url": f"/api/turns/{turn.id}/events",
    }


@router.get("/turns/{turn_id}")
async def get_turn(request: Request, turn_id: str) -> dict[str, object]:
    return _chat(request).serialize_turn(_chat(request).get_turn(turn_id))


@router.get("/turns/{turn_id}/events")
async def turn_events(
    request: Request,
    turn_id: str,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    turn = _chat(request).get_turn(turn_id)
    return StreamingResponse(
        _event_stream(
            request,
            turn.events,
            request.app.state.settings.sse_heartbeat_seconds,
            _event_id(last_event_id),
            {"turn.completed", "turn.failed", "turn.cancelled"},
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/turns/{turn_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_turn(request: Request, turn_id: str) -> dict[str, str]:
    await _chat(request).cancel_turn(turn_id)
    return {"turn_id": turn_id, "status": "cancelling"}
