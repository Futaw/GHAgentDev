from backend.scripts.verify_generation_sandbox import assess_probes


def evidence():
    rows = {
        name: {"status": "error", "errno": 1}
        for name in (
            "sibling",
            "outside",
            "auth_sentinel",
            "update",
            "create",
            "delete",
            "rename",
            "git_write",
            "loopback",
            "public",
        )
    }
    rows["allowed"] = {"status": "read", "sha256": "expected"}
    return rows


def test_empty_or_boolean_claims_never_pass():
    for observed in ({}, {"safe": True}, [], None):
        assert all(
            value["status"] == "inconclusive"
            for value in assess_probes(observed, "expected", True).values()
        )


def test_controls_and_explicit_os_denials_are_required():
    observed = evidence()
    assert all(
        value["status"] == "passed" for value in assess_probes(observed, "expected", True).values()
    )
    assert assess_probes(observed, "expected", False)["command_network"]["status"] == "inconclusive"
    observed["public"]["errno"] = 60  # ETIMEDOUT is not permission denial.
    assert assess_probes(observed, "expected", True)["command_network"]["status"] == "inconclusive"
    observed["sibling"] = {"status": "read", "sha256": "secret"}
    assert assess_probes(observed, "expected", True)["sandbox_read"]["status"] == "failed"
    observed["delete"] = {"status": "changed"}
    assert assess_probes(observed, "expected", True)["non_modification"]["status"] == "failed"


async def test_native_timeout_retains_prior_result_and_progress(monkeypatch, tmp_path, capsys):
    from backend.app.codex.process import CommandResult, CommandTimeout
    from backend.scripts.verify_generation_sandbox import native_probes

    calls = []

    async def command(executable, args, cwd, timeout_seconds, *, progress):
        calls.append(args)
        progress("start", {})
        if "/bin/rm" in args:
            progress("timeout", {})
            raise CommandTimeout({"status": "passed"})
        return CommandResult(
            0, b"fixture-content", b"repospec_probe_command_started\n", {"status": "passed"}
        )

    monkeypatch.setattr("backend.scripts.verify_generation_sandbox.run_command", command)
    rows = {}
    await native_probes(
        "fake",
        [],
        tmp_path,
        tmp_path,
        {"reads": {"allowed": "fixture"}, "network": {}},
        0.01,
        selected={"allowed", "delete"},
        observed=rows,
    )
    assert rows["allowed"]["status"] == "read"
    assert rows["delete"]["status"] == "timeout"
    captured = capsys.readouterr()
    assert captured.out == ""
    assert '"check": "delete"' in captured.err and '"event": "timeout"' in captured.err
    assert "fixture-content" not in captured.err


async def test_sandbox_launch_denial_is_not_operation_denial(monkeypatch, tmp_path):
    from backend.app.codex.process import CommandResult
    from backend.scripts.verify_generation_sandbox import native_probes

    async def command(*args, **kwargs):
        return CommandResult(71, b"", b"Operation not permitted", {"status": "passed"})

    monkeypatch.setattr("backend.scripts.verify_generation_sandbox.run_command", command)
    rows = await native_probes(
        "fake", [], tmp_path, tmp_path, {"reads": {}, "network": {}}, 1, selected={"delete"}
    )
    assert rows["delete"]["status"] == "unavailable"


def test_partial_read_violation_is_retained_and_bad_cleanup_never_passes():
    observed = {"sibling": {"status": "read"}}
    assert assess_probes(observed, "expected", True)["sandbox_read"]["status"] == "failed"
    rows = evidence()
    rows["delete"]["cleanup"] = {"status": "failed"}
    assert assess_probes(rows, "expected", True)["non_modification"]["status"] == "inconclusive"


async def test_early_failure_still_returns_report(monkeypatch):
    import argparse
    import os

    from backend.scripts.verify_generation_sandbox import verify

    async def command(*args, **kwargs):
        raise FileNotFoundError("not logged")

    old_home = os.environ.get("CODEX_HOME")
    monkeypatch.setattr("backend.scripts.verify_generation_sandbox.cli_output", command)
    report = await verify(argparse.Namespace(codex="missing", timeout=1, only="deletion"))
    assert report["failed_check"] == "fixture_setup"
    assert report["behavior_gate"] is False
    assert report["fixture_cleanup"] != "passed"
    assert os.environ.get("CODEX_HOME") == old_home


def test_failed_deletion_control_never_passes_mutation_gate():
    assert (
        assess_probes(evidence(), "expected", True, False)["non_modification"]["status"]
        == "inconclusive"
    )


def test_partial_success_never_exits_zero(monkeypatch, capsys):
    import json

    from backend.scripts.verify_generation_sandbox import main

    async def verified(arguments):
        return {
            "partial": True,
            "protocol_config_gate": True,
            "behavior_gate": True,
            "process_cleanup": "passed",
            "fixture_cleanup": "passed",
        }

    monkeypatch.setattr("backend.scripts.verify_generation_sandbox.verify", verified)
    monkeypatch.setattr("sys.argv", ["verify", "--only", "deletion"])
    assert main() == 1
    assert json.loads(capsys.readouterr().out)["partial"] is True


async def test_execution_error_retains_failed_cleanup(monkeypatch, tmp_path):
    from backend.scripts.verify_generation_sandbox import native_probes

    async def command(*args, **kwargs):
        error = OSError("never log output")
        error.cleanup = {"status": "failed"}
        raise error

    monkeypatch.setattr("backend.scripts.verify_generation_sandbox.run_command", command)
    rows = await native_probes(
        "fake", [], tmp_path, tmp_path, {"reads": {}, "network": {}}, 1, selected={"delete"}
    )
    assert rows["delete"]["cleanup"]["status"] == "failed"
