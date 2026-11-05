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
    assert 'shell_environment_policy.include_only=["PATH"]' in validation
    assert "shell_environment_policy.exclude=[]" in validation


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


def test_runtime_package_manifest_and_path_are_pinned(monkeypatch, tmp_path):
    from backend.app.codex.contract import verify_runtime_package

    tools = tmp_path / "codex-path"
    tools.mkdir()
    (tools / "rg").write_text("fixture")
    monkeypatch.setattr("backend.app.codex.contract.CLI_TOOL_PATH", str(tools))
    manifest = {
        "layoutVersion": 1,
        "version": "0.164.0",
        "target": "aarch64-apple-darwin",
        "variant": "codex",
        "entrypoint": "bin/codex",
        "resourcesDir": "codex-resources",
        "pathDir": "codex-path",
    }
    path = tmp_path / "codex-package.json"
    path.write_text(json.dumps(manifest))
    assert len(verify_runtime_package()) == 64
    manifest["pathDir"] = "unreviewed-tools"
    path.write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match="package_unreviewed"):
        verify_runtime_package()
    link = tmp_path / "link"
    link.symlink_to(tools, target_is_directory=True)
    monkeypatch.setattr("backend.app.codex.contract.CLI_TOOL_PATH", str(link))
    with pytest.raises(RuntimeError, match="path_unreviewed"):
        verify_runtime_package()
