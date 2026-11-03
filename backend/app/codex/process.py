"""Bounded POSIX command lifecycle, scoped to a fresh session per invocation.

Descendants that deliberately escape the session cannot be proven stopped by this
helper. Missing pipe EOF or a surviving group is reported as cleanup failure.
"""

from __future__ import annotations

import asyncio
import math
import os
import signal
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

Progress = Callable[[str, dict], None]
TERM_GRACE = 0.3
KILL_GRACE = 1.0
DRAIN_GRACE = 0.5


class ProcessCleanupError(RuntimeError):
    def __init__(self, cleanup: dict):
        super().__init__("process_cleanup_unconfirmed")
        self.cleanup = cleanup


class CommandTimeout(TimeoutError):
    def __init__(self, cleanup: dict):
        super().__init__("command_timeout")
        self.cleanup = cleanup


@dataclass
class CommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    cleanup: dict


def group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def signal_group(pgid: int, sig: signal.Signals) -> None:
    # pgid is only ever the PID returned by start_new_session=True, never user input.
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass


async def stop_group(process: asyncio.subprocess.Process, emit: Progress) -> dict:
    pgid = process.pid
    errors = False
    for sig, grace in ((signal.SIGTERM, TERM_GRACE), (signal.SIGKILL, KILL_GRACE)):
        if not group_exists(pgid):
            break
        emit("cleanup_signal", {"pid": process.pid, "pgid": pgid, "signal": sig.name})
        try:
            signal_group(pgid, sig)
        except OSError:
            errors = True
        deadline = asyncio.get_running_loop().time() + grace
        while group_exists(pgid) and asyncio.get_running_loop().time() < deadline:  # noqa: ASYNC110
            await asyncio.sleep(0.02)
    return {
        "pid": process.pid,
        "pgid": pgid,
        "group_absent": not group_exists(pgid),
        "parent_returncode": process.returncode,
        "signal_error": errors,
    }


async def close_process(process: asyncio.subprocess.Process) -> dict:
    """For a session with independent stream readers (the App Server transport)."""
    details = await stop_group(process, lambda event, details: None)
    deadline = asyncio.get_running_loop().time() + DRAIN_GRACE
    while (not process.stdout.at_eof() or not process.stderr.at_eof()) and (  # noqa: ASYNC110
        asyncio.get_running_loop().time() < deadline
    ):
        await asyncio.sleep(0.02)
    details["pipes_eof"] = process.stdout.at_eof() and process.stderr.at_eof()
    process._transport.close()
    try:
        await asyncio.wait_for(process.wait(), DRAIN_GRACE)
    except TimeoutError:
        pass
    details["parent_returncode"] = process.returncode
    details["status"] = (
        "passed"
        if details["group_absent"]
        and details["pipes_eof"]
        and process.returncode is not None
        and not details["signal_error"]
        else "failed"
    )
    if details["status"] != "passed":
        raise ProcessCleanupError(details)
    return details


async def run_command(
    executable: str,
    args: list[str],
    cwd: Path,
    timeout_seconds: float,
    *,
    env: dict[str, str] | None = None,
    progress: Progress | None = None,
) -> CommandResult:
    if os.name != "posix":
        raise RuntimeError("process_sessions_unsupported")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_must_be_positive")
    emit = progress or (lambda event, details: None)
    emit("start", {})
    # Shield acquisition so cancellation during spawn cannot lose the process handle.
    spawn = asyncio.create_task(
        asyncio.create_subprocess_exec(
            executable,
            *args,
            cwd=cwd,
            env=env,
            start_new_session=True,
            # Commands never consume user input. Inheriting a terminal lets tools
            # such as macOS rm wait for confirmation while stderr is captured.
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    )
    cancelled = False
    while True:
        try:
            process = await asyncio.shield(spawn)
            break
        except asyncio.CancelledError:
            cancelled = True
        except OSError:
            emit("start_failed", {})
            raise
    emit("spawned", {"pid": process.pid, "pgid": process.pid})
    communication = asyncio.create_task(process.communicate())
    failure: BaseException | None = asyncio.CancelledError() if cancelled else None
    output = (b"", b"")
    if failure is None:
        try:
            output = await asyncio.wait_for(asyncio.shield(communication), timeout_seconds)
        except (Exception, asyncio.CancelledError) as exc:
            failure = exc
    if failure is not None:
        emit(
            "interrupted"
            if isinstance(failure, asyncio.CancelledError)
            else "timeout"
            if isinstance(failure, TimeoutError)
            else "failed",
            {
                "pid": process.pid,
                "pgid": process.pid,
                "parent_returncode": process.returncode,
                "stdout_eof": process.stdout.at_eof(),
                "stderr_eof": process.stderr.at_eof(),
            },
        )

    async def cleanup() -> dict:
        details = await stop_group(process, emit)
        try:
            await asyncio.wait_for(asyncio.shield(communication), DRAIN_GRACE)
            pipes_eof = True
        except Exception:
            pipes_eof = False
        details["pipes_eof"] = pipes_eof
        details["parent_returncode"] = process.returncode
        details["status"] = (
            "passed"
            if details["group_absent"]
            and pipes_eof
            and process.returncode is not None
            and not details["signal_error"]
            else "failed"
        )
        if not communication.done():
            communication.cancel()
        # asyncio exposes no public Process pipe-close API. Close the transport
        # after bounded draining so escaped pipe holders cannot block loop shutdown.
        process._transport.close()
        await asyncio.wait({communication}, timeout=DRAIN_GRACE)
        if communication.done() and not communication.cancelled():
            communication.exception()
        emit("cleanup", details)
        return details

    cleanup_task = asyncio.create_task(cleanup())
    while True:
        try:
            details = await asyncio.shield(cleanup_task)
            break
        except asyncio.CancelledError as exc:
            failure = exc
    if isinstance(failure, asyncio.CancelledError):
        failure.cleanup = details
        raise failure
    if isinstance(failure, TimeoutError):
        raise CommandTimeout(details) from failure
    if failure is not None:
        failure.cleanup = details
        raise failure
    if details["status"] != "passed":
        raise ProcessCleanupError(details)
    emit("complete", {"exit_code": process.returncode})
    return CommandResult(process.returncode, *output, details)
