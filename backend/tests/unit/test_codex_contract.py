import json
from pathlib import Path

import pytest

from backend.app.codex.contract import FIELDS, verify_contract
from backend.app.codex.policy import DISABLED_FEATURES, startup_arguments


def test_startup_policy_is_fixed_and_validation_omits_transport():
    args = startup_arguments()
    assert args[:4] == ["app-server", "--strict-config", "--listen", "stdio://"]
    assert args.count("--disable") == len(DISABLED_FEATURES)
    assert all(args[args.index(feature) - 1] == "--disable" for feature in DISABLED_FEATURES)
    validation = startup_arguments(validation=True)
    assert "--listen" not in validation
    assert "--print-startup-config" in validation
    assert 'shell_environment_policy.inherit="none"' in validation


@pytest.mark.asyncio
async def test_unreviewed_version_does_not_fall_back(monkeypatch, tmp_path):
    calls = []

    async def output(executable, args, cwd, timeout_seconds):
        calls.append((executable, args))
        return b"codex-cli 9.9.9"

    monkeypatch.setattr("backend.app.codex.contract.cli_output", output)
    with pytest.raises(RuntimeError, match="unreviewed"):
        await verify_contract("/fixed/codex", tmp_path, 1)
    assert calls == [("/fixed/codex", ["--version"])]


@pytest.mark.asyncio
async def test_schema_missing_required_runtime_field_is_rejected(monkeypatch, tmp_path):
    async def output(executable, args, cwd, timeout_seconds):
        if args == ["--version"]:
            return b"codex-cli 0.164.0"
        if args == ["app-server", "--help"]:
            return b"--strict-config --disable --print-startup-config --listen"
        if args == ["features", "list"]:
            return "\n".join(DISABLED_FEATURES).encode()
        if "generate-json-schema" in args:
            root = Path(args[args.index("--out") + 1]) / "v2"
            root.mkdir(parents=True)
            for name, fields in FIELDS.items():
                filename = {
                    "ConfigRequirements": "ConfigRequirementsReadResponse",
                    "McpServerStatus": "ListMcpServerStatusResponse",
                }.get(name, name)
                schema = {"properties": dict.fromkeys(fields, {})}
                if name == "ThreadStartResponse":
                    schema["properties"].pop("activePermissionProfile")
                if filename != name:
                    schema = {"definitions": {name: schema}}
                (root / (filename + ".json")).write_text(json.dumps(schema))
        return b"{}"

    monkeypatch.setattr("backend.app.codex.contract.cli_output", output)
    with pytest.raises(RuntimeError, match="schema_fields_missing"):
        await verify_contract("/fixed/codex", tmp_path, 1)
