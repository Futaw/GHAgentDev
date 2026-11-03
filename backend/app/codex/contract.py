"""Fail closed when the installed CLI differs from the reviewed wire contract."""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
from pathlib import Path

from backend.app.codex.policy import DISABLED_FEATURES, startup_arguments

# Deliberately pinned: a CLI update needs a contract review and new behavior gates.
SUPPORTED_VERSION = "codex-cli 0.164.0"
FIELDS = {
    "ThreadStartParams": {"config", "cwd", "ephemeral", "approvalPolicy", "developerInstructions"},
    "TurnStartParams": {"threadId", "input", "approvalPolicy", "outputSchema"},
    "ThreadStartResponse": {
        "activePermissionProfile",
        "runtimeWorkspaceRoots",
        "instructionSources",
        "cwd",
    },
    "ConfigReadParams": {"cwd", "includeLayers"},
    "ConfigReadResponse": {"config", "origins", "layers"},
    "ConfigRequirements": {
        "allowedPermissionProfiles",
        "defaultPermissions",
        "featureRequirements",
    },
    "ExperimentalFeatureListParams": {"threadId", "cursor", "limit"},
    "ListMcpServerStatusParams": {"threadId", "cursor", "limit", "detail"},
    "McpServerStatus": {"runtimeStatus", "tools", "resources", "resourceTemplates", "pluginId"},
}


class CliExecutionError(RuntimeError):
    def __init__(self, exit_code: int) -> None:
        super().__init__("cli_command_rejected")
        self.exit_code = exit_code


async def cli_output(
    executable: str,
    args: list[str],
    cwd: Path,
    timeout_seconds: float,
    *,
    env: dict[str, str] | None = None,
) -> bytes:
    process = await asyncio.create_subprocess_exec(
        executable,
        *args,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout_seconds)
        if process.returncode != 0:
            raise CliExecutionError(process.returncode)
        return stdout
    finally:
        if process.returncode is None:
            process.kill()
            await process.communicate()


async def verify_contract(executable: str, cwd: Path, timeout_seconds: float) -> dict:
    version = (await cli_output(executable, ["--version"], cwd, timeout_seconds)).decode().strip()
    if version != SUPPORTED_VERSION:
        raise RuntimeError("cli_version_unreviewed")
    help_text = (
        await cli_output(executable, ["app-server", "--help"], cwd, timeout_seconds)
    ).decode()
    if not all(
        flag in help_text
        for flag in ("--strict-config", "--disable", "--print-startup-config", "--listen")
    ):
        raise RuntimeError("cli_flags_missing")
    features = (await cli_output(executable, ["features", "list"], cwd, timeout_seconds)).decode()
    if not set(DISABLED_FEATURES) <= {
        line.split()[0] for line in features.splitlines() if line.split()
    }:
        raise RuntimeError("cli_features_missing")
    hashes = {}
    pair_hashes = {}
    with tempfile.TemporaryDirectory(prefix="repospec-schema-") as directory:
        for mode in ("stable", "experimental"):
            root = Path(directory) / mode
            args = ["app-server", "generate-json-schema", "--out", str(root)]
            if mode == "experimental":
                args.append("--experimental")
            await cli_output(executable, args, cwd, timeout_seconds)
            pair_hashes[mode] = hashlib.sha256(
                (root / "v2" / "ThreadStartParams.json").read_bytes()
                + (root / "v2" / "TurnStartParams.json").read_bytes()
            ).hexdigest()
            digest = hashlib.sha256()
            for name, fields in FIELDS.items():
                filename = {
                    "ConfigRequirements": "ConfigRequirementsReadResponse",
                    "McpServerStatus": "ListMcpServerStatusResponse",
                }.get(name, name)
                raw = (root / "v2" / f"{filename}.json").read_bytes()
                schema = json.loads(raw)
                if filename != name:
                    schema = schema["definitions"][name]
                # Runtime provenance is experimental, only check it on that surface.
                if mode == "experimental" or name != "ThreadStartResponse":
                    if not fields <= set(schema.get("properties", {})):
                        raise RuntimeError("cli_schema_fields_missing")
                digest.update(raw)
            hashes[mode] = digest.hexdigest()
    await cli_output(executable, startup_arguments(validation=True), cwd, timeout_seconds)
    return {"version": version, "schema_hashes": hashes, "thread_turn_schema_hashes": pair_hashes}
