from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from backend.app.settings import Settings

logger = logging.getLogger(__name__)

NotificationHandler = Callable[[str, dict[str, Any]], Awaitable[None]]

_SECRET_PATTERNS = (
    re.compile(r"(?i)(access[_ -]?token|refresh[_ -]?token|authorization)[=: ]+[^\s,]+"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
)


def _sanitize_log_line(line: str) -> str:
    sanitized = line
    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


class CodexConnectionError(RuntimeError):
    pass


class CodexRpcError(RuntimeError):
    def __init__(self, code: int | None, message: str) -> None:
        super().__init__(message)
        self.code = code


class CodexAppServer:
    """Small JSONL client with lifecycle supervision for `codex app-server`."""

    def __init__(self, config: Settings) -> None:
        self._config = config
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._supervisor_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._handlers: list[NotificationHandler] = []
        self._request_id = 0
        self._write_lock = asyncio.Lock()
        self._lifecycle_lock = asyncio.Lock()
        self._stopping = False
        self._connected = False
        self._last_error: str | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def add_notification_handler(self, handler: NotificationHandler) -> None:
        self._handlers.append(handler)

    async def start(self) -> None:
        self._stopping = False
        try:
            await self._connect()
        except Exception as exc:
            self._last_error = _sanitize_log_line(str(exc))
            logger.warning("Codex App Server initial connection failed: %s", self._last_error)
        self._supervisor_task = asyncio.create_task(self._supervise(), name="codex-supervisor")

    async def stop(self) -> None:
        self._stopping = True
        process = self._process
        if process and process.returncode is None:
            process.terminate()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=5)
            if process.returncode is None:
                process.kill()
                await process.wait()
        for task in (self._reader_task, self._stderr_task, self._supervisor_task):
            if task and not task.done():
                task.cancel()
        await asyncio.gather(
            *(
                task
                for task in (self._reader_task, self._stderr_task, self._supervisor_task)
                if task
            ),
            return_exceptions=True,
        )
        await self._handle_disconnect("Codex App Server stopped")

    async def ensure_connected(self) -> None:
        if self.connected:
            return
        await self._connect()

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._process or self._process.returncode is not None:
            raise CodexConnectionError("Codex App Server is unavailable")
        self._request_id += 1
        request_id = self._request_id
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._send({"method": method, "id": request_id, "params": params or {}})
            response = await asyncio.wait_for(
                future,
                timeout=self._config.codex_request_timeout_seconds,
            )
        except TimeoutError as exc:
            raise CodexConnectionError(f"Codex request timed out: {method}") from exc
        finally:
            self._pending.pop(request_id, None)
        if error := response.get("error"):
            raise CodexRpcError(error.get("code"), error.get("message", "Codex request failed"))
        result = response.get("result", {})
        return result if isinstance(result, dict) else {"value": result}

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        await self._send({"method": method, "params": params or {}})

    async def _connect(self) -> None:
        async with self._lifecycle_lock:
            if self.connected:
                return
            if self._process and self._process.returncode is None:
                return
            self._process = await asyncio.create_subprocess_exec(
                self._config.codex_executable,
                "app-server",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._reader_task = asyncio.create_task(self._read_stdout(), name="codex-stdout")
            self._stderr_task = asyncio.create_task(self._read_stderr(), name="codex-stderr")
            try:
                await self.request(
                    "initialize",
                    {
                        "clientInfo": {
                            "name": self._config.codex_client_name,
                            "title": self._config.codex_client_title,
                            "version": self._config.codex_client_version,
                        },
                        "capabilities": {"experimentalApi": False},
                    },
                )
                await self.notify("initialized")
            except Exception:
                process = self._process
                if process and process.returncode is None:
                    process.terminate()
                    await process.wait()
                raise
            self._connected = True
            self._last_error = None
            await self._dispatch("app_server/connected", {})
            logger.info("Codex App Server initialized")

    async def _supervise(self) -> None:
        while not self._stopping:
            process = self._process
            if process and process.returncode is None:
                await process.wait()
                if self._stopping:
                    break
                await self._handle_disconnect("Codex App Server exited unexpectedly")
            await asyncio.sleep(self._config.codex_restart_delay_seconds)
            if self._stopping:
                break
            try:
                await self._connect()
            except Exception as exc:
                self._last_error = _sanitize_log_line(str(exc))
                logger.warning("Codex App Server restart failed: %s", self._last_error)

    async def _read_stdout(self) -> None:
        process = self._process
        if not process or not process.stdout:
            return
        while line := await process.stdout.readline():
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Ignoring malformed JSON from Codex App Server")
                continue
            if "id" in message and "method" not in message:
                future = self._pending.get(message["id"])
                if future and not future.done():
                    future.set_result(message)
                else:
                    logger.warning("Ignoring response with unknown request id")
            elif "id" in message and "method" in message:
                await self._handle_server_request(message)
            elif method := message.get("method"):
                params = message.get("params")
                await self._dispatch(method, params if isinstance(params, dict) else {})
        if process is self._process and not self._stopping:
            await self._handle_disconnect("Codex App Server closed its output stream")

    async def _read_stderr(self) -> None:
        process = self._process
        if not process or not process.stderr:
            return
        while line := await process.stderr.readline():
            logger.info(
                "codex app-server: %s", _sanitize_log_line(line.decode(errors="replace").rstrip())
            )

    async def _handle_server_request(self, message: dict[str, Any]) -> None:
        method = message.get("method", "")
        request_id = message["id"]
        if method == "item/commandExecution/requestApproval":
            await self._send({"id": request_id, "result": {"decision": "decline"}})
        elif method == "item/fileChange/requestApproval":
            await self._send({"id": request_id, "result": {"decision": "decline"}})
        elif method in {"execCommandApproval", "applyPatchApproval"}:
            await self._send(
                {
                    "id": request_id,
                    "result": {"decision": {"denied": {"rejection": "Read-only client policy"}}},
                }
            )
        elif method == "item/permissions/requestApproval":
            await self._send({"id": request_id, "result": {"permissions": {}, "scope": "turn"}})
        else:
            await self._send(
                {
                    "id": request_id,
                    "error": {"code": -32601, "message": "Client method is not supported"},
                }
            )
        logger.warning("Rejected Codex server request: %s", method)

    async def _send(self, message: dict[str, Any]) -> None:
        process = self._process
        if not process or process.returncode is not None or not process.stdin:
            raise CodexConnectionError("Codex App Server is unavailable")
        payload = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"
        async with self._write_lock:
            process.stdin.write(payload)
            await process.stdin.drain()

    async def _handle_disconnect(self, reason: str) -> None:
        was_connected = self._connected
        self._connected = False
        self._last_error = reason
        for future in tuple(self._pending.values()):
            if not future.done():
                future.set_exception(CodexConnectionError(reason))
        self._pending.clear()
        if was_connected:
            await self._dispatch("app_server/disconnected", {"reason": reason})

    async def _dispatch(self, method: str, params: dict[str, Any]) -> None:
        results = await asyncio.gather(
            *(handler(method, params) for handler in tuple(self._handlers)),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.error("Codex notification handler failed: %s", result)
