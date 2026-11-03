import asyncio
import os
import signal
import sys
import time
from pathlib import Path

import pytest

from backend.app.codex.contract import CliExecutionError, cli_output
from backend.app.codex.process import CommandTimeout, run_command

# The child keeps both inherited pipes open, ignores TERM, and outlives its parent.
ORPHAN = """
import os, signal, time
child = os.fork()
if child == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    with open("child.pid", "w") as f:
        f.write(str(os.getpid()))
    while True:
        time.sleep(1)
while not os.path.exists("child.pid"):
    time.sleep(.01)
os._exit(0)
"""


def assert_gone(pid):
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.asyncio
async def test_orphan_pipes_timeout_term_kill_and_no_residue(tmp_path):
    events = []
    started = time.monotonic()
    with pytest.raises(CommandTimeout) as caught:
        await run_command(
            sys.executable,
            ["-c", ORPHAN],
            tmp_path,
            0.3,
            progress=lambda event, details: events.append((event, details)),
        )
    assert time.monotonic() - started < 4
    timeout = next(details for event, details in events if event == "timeout")
    assert timeout["parent_returncode"] == 0
    assert not timeout["stdout_eof"] and not timeout["stderr_eof"]
    assert [d["signal"] for e, d in events if e == "cleanup_signal"] == ["SIGTERM", "SIGKILL"]
    assert caught.value.cleanup["status"] == "passed"
    assert_gone(int((tmp_path / "child.pid").read_text()))
    assert_gone(caught.value.cleanup["pid"])


@pytest.mark.asyncio
async def test_cancel_returns_after_cleanup_even_if_cancelled_again(tmp_path):
    task = asyncio.create_task(run_command(sys.executable, ["-c", ORPHAN], tmp_path, 30))
    for _ in range(100):
        if (tmp_path / "child.pid").exists():
            break
        await asyncio.sleep(0.01)
    assert (tmp_path / "child.pid").exists()
    started = time.monotonic()
    task.cancel()
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError) as caught:
        await asyncio.wait_for(task, 4)
    assert time.monotonic() - started < 4
    assert caught.value.cleanup["status"] == "passed"
    assert_gone(int((tmp_path / "child.pid").read_text()))


@pytest.mark.asyncio
async def test_cli_output_and_start_failure(tmp_path):
    assert await cli_output(sys.executable, ["-c", 'print("ok")'], tmp_path, 1) == b"ok\n"
    with pytest.raises(CliExecutionError) as caught:
        await cli_output(sys.executable, ["-c", "raise SystemExit(3)"], tmp_path, 1)
    assert caught.value.exit_code == 3
    with pytest.raises(FileNotFoundError):
        await cli_output(str(tmp_path / "missing"), [], tmp_path, 1)
    with pytest.raises(CommandTimeout):
        await cli_output(sys.executable, ["-c", ORPHAN], tmp_path, 0.3)
    assert_gone(int((tmp_path / "child.pid").read_text()))


@pytest.mark.asyncio
async def test_unconfirmed_group_is_failure_not_success(monkeypatch, tmp_path):
    monkeypatch.setattr("backend.app.codex.process.group_exists", lambda pgid: True)
    # Never signal an unrelated process in a synthetic cleanup failure test.
    monkeypatch.setattr("backend.app.codex.process.signal_group", lambda pgid, sig: None)
    from backend.app.codex.process import ProcessCleanupError

    with pytest.raises(ProcessCleanupError) as caught:
        await run_command(sys.executable, ["-c", "pass"], tmp_path, 1)
    assert caught.value.cleanup["status"] == "failed"


@pytest.mark.asyncio
async def test_escaped_pipe_holder_returns_bounded_failure(tmp_path):
    # A child deliberately leaves the owned group. Never claim it was cleaned up.
    script = ORPHAN.replace(
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)",
        "os.setsid(); signal.signal(signal.SIGTERM, signal.SIG_IGN)",
    )
    started = time.monotonic()
    pid = None
    try:
        with pytest.raises(CommandTimeout) as caught:
            await run_command(sys.executable, ["-c", script], tmp_path, 0.3)
        pid = int((tmp_path / "child.pid").read_text())
        assert time.monotonic() - started < 4
        assert caught.value.cleanup["status"] == "failed"
        assert caught.value.cleanup["pipes_eof"] is False
    finally:
        # Only the exact child created by this fixture is targeted.
        if pid is None and (tmp_path / "child.pid").exists():
            pid = int((tmp_path / "child.pid").read_text())
        if pid:
            os.kill(pid, signal.SIGKILL)
            for _ in range(100):
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                await asyncio.sleep(0.01)
            assert_gone(pid)


@pytest.mark.asyncio
async def test_cancel_during_spawn_keeps_handle_for_cleanup(monkeypatch, tmp_path):
    original = asyncio.create_subprocess_exec
    events = []

    async def delayed_spawn(*args, **kwargs):
        await asyncio.sleep(0.08)
        return await original(*args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_spawn)
    task = asyncio.create_task(
        run_command(
            sys.executable,
            ["-c", "import time; time.sleep(60)"],
            tmp_path,
            30,
            progress=lambda event, details: events.append((event, details)),
        )
    )
    await asyncio.sleep(0.01)
    task.cancel()
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError) as caught:
        await asyncio.wait_for(task, 4)
    assert caught.value.cleanup["status"] == "passed"
    assert_gone(next(details["pid"] for event, details in events if event == "spawned"))


@pytest.mark.asyncio
async def test_sigint_native_probe_returns_json_and_cleans_child(tmp_path):
    import json

    project_root = await asyncio.to_thread(lambda: Path(__file__).resolve().parents[3])

    script = """
import asyncio, json, sys
from pathlib import Path
from backend.scripts.verify_generation_sandbox import native_probes
async def main():
    root = Path(sys.argv[1])
    rows = {}
    try:
        await native_probes(sys.executable, ["-c", sys.argv[2]], root, root,
                            {"reads":{},"network":{}}, 30,
                            selected={"delete"}, observed=rows)
    except asyncio.CancelledError:
        print(json.dumps(rows), flush=True)
        return 130
    return 0
sys.exit(asyncio.run(main()))
"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        script,
        str(tmp_path),
        ORPHAN,
        cwd=project_root,
        start_new_session=True,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        for _ in range(200):
            if (tmp_path / "child.pid").exists():
                break
            await asyncio.sleep(0.01)
        assert (tmp_path / "child.pid").exists()
        os.kill(process.pid, signal.SIGINT)
        stdout, stderr = await asyncio.wait_for(process.communicate(), 4)
        assert process.returncode == 130
        rows = json.loads(stdout)
        assert rows["delete"]["status"] == "interrupted"
        assert rows["delete"]["cleanup"]["status"] == "passed"
        assert b'"event": "interrupted"' in stderr
        assert_gone(int((tmp_path / "child.pid").read_text()))
    finally:
        if process.returncode is None:
            process.kill()
            await asyncio.wait_for(process.wait(), 1)
        path = tmp_path / "child.pid"
        if path.exists():
            try:
                os.kill(int(path.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.asyncio
async def test_timeout_does_not_stop_an_independent_session(tmp_path):
    sentry = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import time; time.sleep(30)",
        start_new_session=True,
    )
    try:
        with pytest.raises(CommandTimeout):
            await run_command(sys.executable, ["-c", ORPHAN], tmp_path, 0.3)
        assert sentry.returncode is None
        os.kill(sentry.pid, 0)
    finally:
        sentry.kill()
        await asyncio.wait_for(sentry.wait(), 1)


@pytest.mark.asyncio
async def test_terminal_caller_cannot_make_rm_wait_for_confirmation(tmp_path):
    """A TTY caller must not leak its input device into noninteractive commands."""
    import json
    import pty

    if os.geteuid() == 0:
        pytest.skip("root can bypass the write-access check used by rm's prompt")
    target = tmp_path / "non-sensitive-readonly.txt"
    target.write_text("disposable fixture")
    target.chmod(0o444)
    project_root = await asyncio.to_thread(lambda: Path(__file__).resolve().parents[3])
    script = """
import asyncio, json, os, sys
from pathlib import Path
from backend.app.codex.process import CommandTimeout, run_command
async def main():
    root = Path(sys.argv[1])
    try:
        result = await run_command('/bin/rm', [str(root/'non-sensitive-readonly.txt')], root, .5)
        report = {'returncode': result.returncode, 'cleanup':result.cleanup}
    except CommandTimeout as exc:
        report = {'timeout': True, 'cleanup':exc.cleanup}
    report['caller_stdin_is_terminal'] = os.isatty(0)
    print(json.dumps(report))
asyncio.run(main())
"""
    master, slave = pty.openpty()
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            str(tmp_path),
            cwd=project_root,
            stdin=slave,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), 4)
        assert process.returncode == 0
        report = json.loads(stdout)
        assert report["caller_stdin_is_terminal"] is True
        assert not report.get("timeout"), report
        assert report["returncode"] == 0
        assert report["cleanup"]["status"] == "passed"
        assert not target.exists()
        assert_gone(report["cleanup"]["pid"])
    finally:
        os.close(slave)
        os.close(master)
        if process and process.returncode is None:
            process.kill()
            await asyncio.wait_for(process.wait(), 1)
