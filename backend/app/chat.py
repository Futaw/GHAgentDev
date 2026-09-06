from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from backend.app.codex import CodexAppServer
from backend.app.events import EventBuffer
from backend.app.settings import Settings


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class Message:
    id: str
    role: Literal["user", "assistant"]
    content: str
    status: str
    created_at: str = field(default_factory=_now)


@dataclass(slots=True)
class ChatSession:
    id: str
    codex_thread_id: str | None
    messages: list[Message] = field(default_factory=list)
    active_turn_id: str | None = None
    created_at: str = field(default_factory=_now)


@dataclass(slots=True)
class ChatTurn:
    id: str
    session_id: str
    status: str
    events: EventBuffer
    codex_turn_id: str | None = None
    error_message: str | None = None
    runner: asyncio.Task[None] | None = None


class ChatConflictError(RuntimeError):
    pass


class ChatNotFoundError(RuntimeError):
    pass


class ChatService:
    def __init__(self, codex: CodexAppServer, config: Settings) -> None:
        self._codex = codex
        self._config = config
        self._sessions: dict[str, ChatSession] = {}
        self._turns: dict[str, ChatTurn] = {}
        self._thread_to_session: dict[str, str] = {}
        codex.add_notification_handler(self._handle_notification)

    async def create_session(self) -> ChatSession:
        session = ChatSession(id=str(uuid4()), codex_thread_id=None)
        self._sessions[session.id] = session
        await self._start_session_thread(session)
        return session

    def get_session(self, session_id: str) -> ChatSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise ChatNotFoundError("Chat session was not found") from exc

    def get_turn(self, turn_id: str) -> ChatTurn:
        try:
            return self._turns[turn_id]
        except KeyError as exc:
            raise ChatNotFoundError("Chat turn was not found") from exc

    async def send_message(self, session_id: str, content: str) -> ChatTurn:
        session = self.get_session(session_id)
        if session.active_turn_id:
            active = self._turns[session.active_turn_id]
            if active.status in {"queued", "running"}:
                raise ChatConflictError("A turn is already running for this session")
        user_message = Message(id=str(uuid4()), role="user", content=content, status="completed")
        assistant_message = Message(
            id=str(uuid4()), role="assistant", content="", status="streaming"
        )
        session.messages.extend((user_message, assistant_message))
        turn = ChatTurn(
            id=str(uuid4()),
            session_id=session_id,
            status="queued",
            events=EventBuffer(self._config.sse_event_buffer_size),
        )
        self._turns[turn.id] = turn
        session.active_turn_id = turn.id
        turn.runner = asyncio.create_task(
            self._start_turn(turn, assistant_message),
            name=f"chat-turn-{turn.id}",
        )
        return turn

    async def cancel_turn(self, turn_id: str) -> None:
        turn = self.get_turn(turn_id)
        session = self.get_session(turn.session_id)
        if turn.status not in {"queued", "running"}:
            return
        if turn.codex_turn_id and session.codex_thread_id:
            await self._codex.request(
                "turn/interrupt",
                {"threadId": session.codex_thread_id, "turnId": turn.codex_turn_id},
            )
        elif turn.runner:
            turn.runner.cancel()
            await self._finish_turn(turn, "cancelled")

    async def _start_turn(self, turn: ChatTurn, assistant_message: Message) -> None:
        session = self.get_session(turn.session_id)
        user_message = session.messages[-2]
        workspace = str(self._config.test_chat_workspace)
        try:
            if not session.codex_thread_id:
                await self._start_session_thread(session)
            result = await self._codex.request(
                "turn/start",
                {
                    "threadId": session.codex_thread_id,
                    "input": [{"type": "text", "text": user_message.content}],
                    "cwd": workspace,
                    "approvalPolicy": "never",
                    "sandboxPolicy": {
                        "type": "readOnly",
                        "networkAccess": False,
                    },
                },
            )
            turn.codex_turn_id = result["turn"]["id"]
            if turn.status == "queued":
                turn.status = "running"
                await turn.events.publish("turn.started", {"turn_id": turn.id})
        except asyncio.CancelledError:
            assistant_message.status = "cancelled"
            raise
        except Exception:
            assistant_message.status = "failed"
            await self._fail_turn(turn, "Codexで回答を開始できませんでした。")

    async def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        if method == "app_server/disconnected":
            for turn in tuple(self._turns.values()):
                if turn.status in {"queued", "running"}:
                    await self._fail_turn(turn, "Codex App Serverとの接続が切断されました。")
            self._thread_to_session.clear()
            for session in self._sessions.values():
                session.codex_thread_id = None
            return
        thread_id = params.get("threadId")
        if not thread_id or thread_id not in self._thread_to_session:
            return
        session = self._sessions[self._thread_to_session[thread_id]]
        if not session.active_turn_id:
            return
        turn = self._turns[session.active_turn_id]
        codex_turn_id = params.get("turnId") or params.get("turn", {}).get("id")
        if turn.codex_turn_id and codex_turn_id and turn.codex_turn_id != codex_turn_id:
            return
        if method == "turn/started":
            turn.codex_turn_id = codex_turn_id
            if turn.status == "queued":
                turn.status = "running"
                await turn.events.publish("turn.started", {"turn_id": turn.id})
        elif method == "item/agentMessage/delta":
            delta = params.get("delta", "")
            if delta:
                session.messages[-1].content += delta
                await turn.events.publish(
                    "message.delta",
                    {"turn_id": turn.id, "delta": delta},
                )
        elif method in {"item/started", "item/completed"}:
            item_type = params.get("item", {}).get("type")
            if item_type and item_type not in {"reasoning", "agentMessage", "userMessage"}:
                event_type = (
                    "activity.started" if method.endswith("started") else "activity.completed"
                )
                await turn.events.publish(
                    event_type,
                    {"turn_id": turn.id, "activity": item_type},
                )
        elif method == "turn/completed":
            status = params.get("turn", {}).get("status")
            if status == "completed":
                await self._finish_turn(turn, "completed")
            elif status == "interrupted":
                await self._finish_turn(turn, "cancelled")
            else:
                await self._fail_turn(turn, "Codexの回答生成に失敗しました。")
        elif method == "error" and not params.get("willRetry", False):
            await self._fail_turn(turn, "Codexの回答生成中にエラーが発生しました。")

    async def _finish_turn(self, turn: ChatTurn, status: str) -> None:
        if turn.status in {"completed", "failed", "cancelled"}:
            return
        turn.status = status
        session = self.get_session(turn.session_id)
        session.active_turn_id = None
        if session.messages and session.messages[-1].role == "assistant":
            session.messages[-1].status = status
        event_type = "turn.completed" if status == "completed" else "turn.cancelled"
        await turn.events.publish(event_type, {"turn_id": turn.id, "status": status})

    async def _fail_turn(self, turn: ChatTurn, message: str) -> None:
        if turn.status in {"completed", "failed", "cancelled"}:
            return
        turn.status = "failed"
        turn.error_message = message
        session = self.get_session(turn.session_id)
        session.active_turn_id = None
        if session.messages and session.messages[-1].role == "assistant":
            session.messages[-1].status = "failed"
        await turn.events.publish(
            "turn.failed",
            {"turn_id": turn.id, "status": "failed", "message": message},
        )

    async def _start_session_thread(self, session: ChatSession) -> None:
        await self._codex.ensure_connected()
        workspace = str(self._config.test_chat_workspace)
        result = await self._codex.request(
            "thread/start",
            {
                "cwd": workspace,
                "approvalPolicy": "never",
                "sandbox": "read-only",
                "ephemeral": True,
                "serviceName": self._config.codex_client_name,
                "developerInstructions": (
                    "This smoke-test thread is strictly read-only. Do not modify files, "
                    "run commands requiring additional permissions, or use network access."
                ),
            },
        )
        session.codex_thread_id = result["thread"]["id"]
        self._thread_to_session[session.codex_thread_id] = session.id

    @staticmethod
    def serialize_session(session: ChatSession) -> dict[str, Any]:
        return {
            "id": session.id,
            "status": "running" if session.active_turn_id else "idle",
            "created_at": session.created_at,
        }

    @staticmethod
    def serialize_message(message: Message) -> dict[str, Any]:
        return {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "status": message.status,
            "created_at": message.created_at,
        }

    @staticmethod
    def serialize_turn(turn: ChatTurn) -> dict[str, Any]:
        return {
            "id": turn.id,
            "session_id": turn.session_id,
            "status": turn.status,
            "error_message": turn.error_message,
        }
