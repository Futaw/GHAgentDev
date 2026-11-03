"""Fail closed when the installed CLI differs from the reviewed wire contract."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from backend.app.codex.policy import DISABLED_FEATURES, startup_arguments
from backend.app.codex.process import Progress, run_command

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
    progress: Progress | None = None,
) -> bytes:
    result = await run_command(executable, args, cwd, timeout_seconds, env=env, progress=progress)
    if result.returncode != 0:
        raise CliExecutionError(result.returncode)
    return result.stdout


async def verify_contract(
    executable: str, cwd: Path, timeout_seconds: float, *, progress: Progress | None = None
) -> dict:
    async def command(name: str, args: list[str]) -> bytes:
        callback = (
            (lambda event, details: progress(event, {"step": name, **details}))
            if progress
            else None
        )
        try:
            if callback:
                return await cli_output(executable, args, cwd, timeout_seconds, progress=callback)
            return await cli_output(executable, args, cwd, timeout_seconds)
        except BaseException as exc:
            if progress:
                progress("timeout" if isinstance(exc, TimeoutError) else "failed", {"step": name})
            raise

    version = (await command("version", ["--version"])).decode().strip()
    if version != SUPPORTED_VERSION:
        raise RuntimeError("cli_version_unreviewed")
    help_text = (await command("app_server_help", ["app-server", "--help"])).decode()
    if not all(
        flag in help_text
        for flag in ("--strict-config", "--disable", "--print-startup-config", "--listen")
    ):
        raise RuntimeError("cli_flags_missing")
    features = (await command("features", ["features", "list"])).decode()
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
            await command("schema_" + mode, args)
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
    await command("startup_validation", startup_arguments(validation=True))
    return {"version": version, "schema_hashes": hashes, "thread_turn_schema_hashes": pair_hashes}
