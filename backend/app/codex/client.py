from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from backend.app.codex.contract import cli_output, verify_contract
from backend.app.codex.policy import startup_arguments
from backend.app.settings import Settings

logger = logging.getLogger(__name__)
PROCESS_CWD = Path(__file__).resolve().parents[3]

NotificationHandler = Callable[[str, dict[str, Any]], Awaitable[None]]

rpc_trace_id: ContextVar[str] = ContextVar("rpc_trace_id", default="startup")


class CodexConnectionError(RuntimeError):
    pass


class CodexTimeoutError(RuntimeError):
    def __init__(self, method: str) -> None:
        super().__init__("Codex request timed out")
        self.method = method


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
        self.rejection_count = 0
        self.generation = 0
        self.security_epoch = 0
        self.contract: dict | None = None
        self._contract_lock = asyncio.Lock()
        self._notification_tasks: set[asyncio.Task] = set()
        self.last_received_at: float | None = None

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
            self._last_error = type(exc).__name__
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
        for task in tuple(self._notification_tasks):
            task.cancel()
        await asyncio.gather(*tuple(self._notification_tasks), return_exceptions=True)

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
        started = time.monotonic()
        outcome = "failed"
        try:
            await self._send({"method": method, "id": request_id, "params": params or {}})
            logger.info(
                "Codex request sent method=%s request_id=%s generation=%s pending=%s trace_id=%s",
                method,
                request_id,
                self.generation,
                len(self._pending),
                rpc_trace_id.get(),
            )
            response = await asyncio.wait_for(
                future,
                timeout=self._config.codex_request_timeout_seconds,
            )
            outcome = "rpc_error" if response.get("error") else "success"
        except TimeoutError as exc:
            outcome = "timeout"
            raise CodexTimeoutError(method) from exc
        finally:
            self._pending.pop(request_id, None)
            logger.info(
                "Codex request finished method=%s request_id=%s generation=%s "
                "outcome=%s elapsed=%.3f trace_id=%s",
                method,
                request_id,
                self.generation,
                outcome,
                time.monotonic() - started,
                rpc_trace_id.get(),
            )
        if error := response.get("error"):
            raise CodexRpcError(error.get("code"), error.get("message", "Codex request failed"))
        if method == "account/logout":
            self.security_epoch += 1
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
            await cli_output(
                self._config.codex_executable,
                startup_arguments(validation=True),
                PROCESS_CWD,
                self._config.codex_request_timeout_seconds,
            )
            self._process = await asyncio.create_subprocess_exec(
                self._config.codex_executable,
                *startup_arguments(),
                cwd=PROCESS_CWD,
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
                        "capabilities": {"experimentalApi": True},
                    },
                )
                await self.notify("initialized")
            except Exception:
                process = self._process
                if process and process.returncode is None:
                    process.terminate()
                    await process.wait()
                raise
            self.generation += 1
            self.security_epoch += 1
            self.contract = None
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
                self._last_error = type(exc).__name__
                logger.warning("Codex App Server restart failed: %s", self._last_error)

    async def _read_stdout(self) -> None:
        process = self._process
        if not process or not process.stdout:
            return
        while line := await process.stdout.readline():
            self.last_received_at = time.monotonic()
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Malformed Codex JSON generation=%s", self.generation)
                continue
            if not isinstance(message, dict):
                logger.warning("Ignoring non-object Codex JSON generation=%s", self.generation)
                continue
            if "id" in message and "method" not in message:
                if type(message["id"]) is not int:
                    logger.warning(
                        "Ignoring invalid Codex response id generation=%s", self.generation
                    )
                    continue
                future = self._pending.get(message["id"])
                if future and not future.done():
                    future.set_result(message)
                else:
                    logger.warning(
                        "Ignoring late or unknown response request_id=%s generation=%s",
                        message["id"],
                        self.generation,
                    )
            elif "id" in message and "method" in message:
                await self._handle_server_request(message)
            elif method := message.get("method"):
                params = message.get("params")
                if method in {"account/updated", "account/login/completed"}:
                    self.security_epoch += 1
                self._queue_notification(method, params if isinstance(params, dict) else {})
        if process is self._process and not self._stopping:
            await self._handle_disconnect("Codex App Server closed its output stream")

    async def _read_stderr(self) -> None:
        process = self._process
        if not process or not process.stderr:
            return
        while line := await process.stderr.readline():
            # Never log raw stderr: it can contain arbitrary config, URLs or credentials.
            logger.debug("Codex stderr received bytes=%s generation=%s", len(line), self.generation)

    async def _handle_server_request(self, message: dict[str, Any]) -> None:
        self.rejection_count += 1
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
        category = (
            method
            if method
            in {
                "item/commandExecution/requestApproval",
                "item/fileChange/requestApproval",
                "item/permissions/requestApproval",
                "execCommandApproval",
                "applyPatchApproval",
            }
            else "unsupported"
        )
        logger.warning("Rejected Codex server request category=%s", category)
        context = message.get("params")
        details = dict(context) if isinstance(context, dict) else {}
        details["method"] = method
        self._queue_notification("app_server/server_request_rejected", details)

    async def _send(self, message: dict[str, Any]) -> None:
        process = self._process
        if not process or process.returncode is not None or not process.stdin:
            raise CodexConnectionError("Codex App Server is unavailable")
        payload = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"
        async with self._write_lock:
            process.stdin.write(payload)
            await process.stdin.drain()

    async def _handle_disconnect(self, reason: str) -> None:
        logger.info(
            "Codex disconnected generation=%s pending=%s exit_code=%s last_received=%s",
            self.generation,
            len(self._pending),
            self._process.returncode if self._process else None,
            self.last_received_at,
        )
        was_connected = self._connected
        self._connected = False
        self.security_epoch += 1
        self.contract = None
        self._last_error = reason
        for future in tuple(self._pending.values()):
            if not future.done():
                future.set_exception(CodexConnectionError(reason))
        self._pending.clear()
        if was_connected:
            self._queue_notification("app_server/disconnected", {"reason": reason})

    async def ensure_generation_contract(self) -> None:
        async with self._contract_lock:
            generation = self.generation
            if self.contract is None:
                contract = await verify_contract(
                    self._config.codex_executable,
                    PROCESS_CWD,
                    self._config.codex_request_timeout_seconds,
                )
                if not self.connected or generation != self.generation:
                    raise CodexConnectionError("Connection changed during contract inspection")
                self.contract = contract

    async def discard_connection(self) -> None:
        process = self._process
        await self._handle_disconnect("Codex connection discarded")
        if process and process.returncode is None:
            process.kill()
            await process.wait()

    def _queue_notification(self, method: str, params: dict[str, Any]) -> None:
        generation = self.generation

        async def deliver() -> None:
            if generation == self.generation:
                await self._dispatch(method, params)

        task = asyncio.create_task(deliver())
        self._notification_tasks.add(task)
        task.add_done_callback(self._notification_tasks.discard)

    async def _dispatch(self, method: str, params: dict[str, Any]) -> None:
        started = time.monotonic()
        logger.debug("Codex notification started method=%s generation=%s", method, self.generation)
        results = await asyncio.gather(
            *(handler(method, params) for handler in tuple(self._handlers)),
            return_exceptions=True,
        )
        logger.debug(
            "Codex notification completed method=%s generation=%s elapsed=%.3f",
            method,
            self.generation,
            time.monotonic() - started,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.error(
                    "Codex notification handler failed classification=%s", type(result).__name__
                )
