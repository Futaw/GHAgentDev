from __future__ import annotations

import logging
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import UUID

from backend.app.codex.policy import DISABLED_FEATURES, SAFE_PATH

LOGGER = logging.getLogger(__name__)


class GenerationSecurityError(RuntimeError):
    """Only fixed classifications and sanitized diagnostics belong here."""

    def __init__(self, reason: str, diagnostics: dict | None = None):
        super().__init__(reason)
        self.diagnostics = diagnostics


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise GenerationSecurityError(reason)


def permission_profile_name(job_id: UUID) -> str:
    return f"repospec_generation_{job_id.hex}"


def generation_thread_config(job_id: UUID, effective_config: dict) -> dict[str, Any]:
    profile = permission_profile_name(job_id)
    require(profile not in (effective_config.get("permissions") or {}), "profile_collision")
    return {
        "default_permissions": profile,
        "permissions": {
            profile: {
                "description": "RepoSpec Viewer Generation read-only access",
                "filesystem": {
                    ":root": "deny",
                    ":minimal": "read",
                    ":workspace_roots": {".": "read"},
                },
                "network": {"enabled": False},
            }
        },
        "web_search": "disabled",
        "project_doc_max_bytes": 0,
        "apps": {
            name: {"enabled": False} for name in {"_default", *(effective_config.get("apps") or {})}
        },
        "mcp_servers": {name: {"enabled": False} for name in effective_config["mcp_servers"]},
    }


SHELL_FIELDS = (
    "inherit",
    "ignore_default_excludes",
    "set",
    "include_only",
    "exclude",
    "filters",
    "experimental_use_profile",
)
SOURCE_TYPES = {
    "packagedDefaults",
    "mdm",
    "system",
    "enterpriseManaged",
    "user",
    "project",
    "sessionFlags",
    "legacyManagedConfigTomlFromFile",
    "legacyManagedConfigTomlFromMdm",
}


def shell_environment_diagnostics(config_read: dict) -> dict:
    """No environment names, values, patterns, paths or layer versions escape."""
    shell = config_read.get("config", {}).get("shell_environment_policy")
    if not isinstance(shell, dict):
        return {"table_present": False}
    matches = {
        "inherit": shell.get("inherit") == "none",
        "ignore_default_excludes": shell.get("ignore_default_excludes") is False,
        "set": shell.get("set") == {"PATH": SAFE_PATH},
        "include_only": shell.get("include_only") in (None, []),
        "exclude": shell.get("exclude") in (None, []),
        "filters": shell.get("filters") in (None, []),
        "experimental_use_profile": shell.get("experimental_use_profile") in (None, False),
    }
    fields = {}
    for field in SHELL_FIELDS:
        sources = []
        for layer in config_read.get("layers", []):
            table = layer.get("config", {}).get("shell_environment_policy", {})
            if isinstance(table, dict) and field in table:
                kind = layer.get("name", {}).get("type")
                sources.append(
                    {
                        "type": kind if kind in SOURCE_TYPES else "unknown",
                        "active": layer.get("disabledReason") is None,
                    }
                )
        origin = config_read.get("origins", {}).get("shell_environment_policy." + field, {})
        kind = origin.get("name", {}).get("type") if isinstance(origin, dict) else None
        fields[field] = {
            "matches": matches[field],
            "present": field in shell,
            "layer_sources": sources,
            "effective_origin": kind if kind in SOURCE_TYPES else "unreported",
        }
    values = shell.get("set")
    return {
        "table_present": True,
        "fields": fields,
        "unknown_field_count": len(set(shell) - set(SHELL_FIELDS)),
        "set_entry_count": len(values) if isinstance(values, dict) else None,
        "set_path_matches": isinstance(values, dict) and values.get("PATH") == SAFE_PATH,
    }


def assert_security_requirements(
    config_read: dict, requirements_read: dict, profile: str | None = None
) -> dict:
    effective = config_read.get("config")
    require(isinstance(effective, dict), "config_missing")
    require(isinstance(config_read.get("origins"), dict), "origins_missing")
    layers = config_read.get("layers")
    require(isinstance(layers, list) and bool(layers), "layers_missing")
    for layer in layers:
        require(
            isinstance(layer, dict)
            and isinstance(layer.get("version"), str)
            and isinstance(layer.get("name"), dict)
            and layer["name"].get("type")
            in {
                "packagedDefaults",
                "mdm",
                "system",
                "enterpriseManaged",
                "user",
                "project",
                "sessionFlags",
                "legacyManagedConfigTomlFromFile",
                "legacyManagedConfigTomlFromMdm",
            }
            and isinstance(layer.get("config"), dict)
            and (layer.get("disabledReason") is None or isinstance(layer["disabledReason"], str)),
            "layer_invalid",
        )
        if layer.get("disabledReason") is None:
            _check_inherited(layer["config"])
    _check_inherited(effective)
    features = effective.get("features")
    require(isinstance(features, dict), "features_missing")
    require(all(features.get(name) is False for name in DISABLED_FEATURES), "features_enabled")
    require(effective.get("web_search") == "disabled", "web_search_enabled")
    require(
        type(effective.get("project_doc_max_bytes")) is int
        and effective["project_doc_max_bytes"] == 0,
        "project_instructions_enabled",
    )
    require(effective.get("allow_login_shell") is False, "login_shell_enabled")
    shell = effective.get("shell_environment_policy")
    require(isinstance(shell, dict), "shell_environment_missing")
    require(
        set(shell)
        <= {
            "inherit",
            "ignore_default_excludes",
            "set",
            "include_only",
            "exclude",
            "filters",
            "experimental_use_profile",
        },
        "shell_environment_unknown",
    )
    diagnostics = shell_environment_diagnostics(config_read)
    if not all(field["matches"] for field in diagnostics["fields"].values()):
        LOGGER.warning("Generation shell environment mismatch diagnostics=%s", diagnostics)
        raise GenerationSecurityError("shell_environment_merge", diagnostics)
    require(isinstance(effective.get("mcp_servers"), dict), "mcp_inventory_missing")
    require(effective.get("apps") is None or isinstance(effective["apps"], dict), "apps_invalid")
    require("requirements" in requirements_read, "requirements_missing")
    requirements = requirements_read["requirements"]
    if requirements is not None:
        require(isinstance(requirements, dict), "requirements_invalid")
        for key, value in requirements.items():
            if value is None:
                continue
            if key in {"allowedApprovalPolicies", "allowedWebSearchModes"}:
                expected = "never" if key == "allowedApprovalPolicies" else "disabled"
                require(isinstance(value, list) and expected in value, "requirements_allowlist")
            elif key == "featureRequirements":
                require(
                    isinstance(value, dict)
                    and all(
                        name in DISABLED_FEATURES and enabled is False
                        for name, enabled in value.items()
                    ),
                    "requirements_features",
                )
            elif key == "allowedPermissionProfiles":
                require(
                    isinstance(value, dict) and profile is not None and value.get(profile) is True,
                    "requirements_profile",
                )
            elif key == "defaultPermissions":
                require(profile is not None and value == profile, "requirements_default_profile")
            elif key in {
                "allowLoginShell",
                "allowBrowserAndComputerUse",
                "allowRemoteControl",
                "allowAppshots",
            }:
                require(value is False, "requirements_external_access")
            else:
                # Unimplemented managed constraints are never silently accepted.
                raise GenerationSecurityError("requirements_unevaluated")
    return deepcopy(effective)


def _check_inherited(config: dict) -> None:
    for key in ("sandbox_mode", "sandbox_workspace_write"):
        require(config.get(key) is None, "legacy_sandbox")
    for key in (
        "instructions",
        "developer_instructions",
        "model_instructions_file",
        "experimental_instructions_file",
        "compact_prompt",
        "agents",
        "agent",
        "project_doc_fallback_filenames",
    ):
        require(config.get(key) in (None, "", [], {}), "inherited_instructions")
    require(config.get("project_root_markers") in (None, [], [".git"]), "project_roots_custom")
    profiles = config.get("permissions")
    require(profiles is None or isinstance(profiles, dict), "profiles_invalid")
    for permission in (profiles or {}).values():
        require(isinstance(permission, dict), "profile_invalid")
        require(permission.get("extends") is None, "profile_extends")
        filesystem = permission.get("filesystem", {})
        require(
            isinstance(filesystem, dict)
            and set(filesystem) <= {":root", ":minimal", ":workspace_roots"},
            "profile_extra_root",
        )
    for key in config:
        if any(
            word in key
            for word in ("instruction", "sandbox", "permission", "workspace_root", "environment")
        ):
            if (
                key
                in {
                    "include_apps_instructions",
                    "include_collaboration_mode_instructions",
                    "include_environment_context",
                    "include_environment_context_time",
                    "include_permissions_instructions",
                }
                and type(config[key]) is bool
            ):
                continue
            if config[key] is None:
                continue
            require(
                key
                in {
                    "instructions",
                    "developer_instructions",
                    "model_instructions_file",
                    "experimental_instructions_file",
                    "sandbox_mode",
                    "sandbox_workspace_write",
                    "permissions",
                    "default_permissions",
                    "shell_environment_policy",
                },
                "unknown_security_setting",
            )


def assert_thread(result: dict, path: Path, profile: str) -> str:
    require(result.get("cwd") == str(path), "thread_cwd")
    require(result.get("approvalPolicy") == "never", "thread_approval")
    require(
        result.get("activePermissionProfile") == {"id": profile, "extends": None}, "thread_profile"
    )
    require(result.get("runtimeWorkspaceRoots") == [str(path)], "thread_roots")
    require(result.get("instructionSources") == [], "thread_instructions")
    thread_id = result.get("thread", {}).get("id")
    require(isinstance(thread_id, str) and bool(thread_id), "thread_id")
    return thread_id


async def inventory(codex: Any, method: str, thread_id: str) -> list[dict]:
    rows: list[dict] = []
    cursor = None
    seen = set()
    while True:
        params = {"threadId": thread_id, "limit": 100, "cursor": cursor}
        if method == "mcpServerStatus/list":
            params["detail"] = "full"
        result = await codex.request(method, params)
        require(
            isinstance(result.get("data"), list) and "nextCursor" in result, "inventory_invalid"
        )
        rows.extend(result["data"])
        cursor = result["nextCursor"]
        if cursor is None:
            return rows
        require(
            isinstance(cursor, str) and bool(cursor) and cursor not in seen and len(seen) < 100,
            "inventory_cursor",
        )
        seen.add(cursor)


async def assert_runtime(codex: Any, thread_id: str, effective: dict) -> None:
    features = await inventory(codex, "experimentalFeature/list", thread_id)
    names: set[str] = set()
    for row in features:
        require(
            isinstance(row, dict)
            and isinstance(row.get("name"), str)
            and type(row.get("enabled")) is bool,
            "feature_invalid",
        )
        name = row["name"]
        require(name not in names, "feature_duplicate")
        names.add(name)
        if name in DISABLED_FEATURES:
            require(row["enabled"] is False, "feature_enabled")
    require(set(DISABLED_FEATURES) <= names, "feature_missing")
    servers = await inventory(codex, "mcpServerStatus/list", thread_id)
    names = set()
    for row in servers:
        require(isinstance(row, dict) and isinstance(row.get("name"), str), "mcp_invalid")
        name = row["name"]
        require(name in effective["mcp_servers"] and name not in names, "mcp_unknown_or_duplicate")
        names.add(name)
        require(
            {"runtimeStatus", "pluginId", "tools", "resources", "resourceTemplates"} <= set(row)
            and row.get("runtimeStatus") == "disabled"
            and row.get("pluginId") is None
            and row.get("tools") == {}
            and row.get("resources") == []
            and row.get("resourceTemplates") == [],
            "mcp_not_disabled",
        )
    require(names == set(effective["mcp_servers"]), "mcp_missing")


class GenerationPreflight:
    """No process-wide config cache; each instance belongs to exactly one Job."""

    def __init__(self, codex: Any, job_id: UUID, path: Path | None = None) -> None:
        self.codex = codex
        self.path = path.resolve() if path else None
        self.job_id = job_id
        self.profile = permission_profile_name(job_id)
        self.epoch = (codex.generation, codex.security_epoch)
        self.rejections = codex.rejection_count
        self.snapshot: tuple[dict, dict] | None = None
        self.effective: dict = {}
        self.thread_id: str | None = None

    def assert_current(self) -> None:
        require(
            self.codex.connected
            and self.epoch == (self.codex.generation, self.codex.security_epoch),
            "inspection_expired",
        )
        require(self.codex.rejection_count == self.rejections, "permission_request_rejected")

    async def read(self) -> tuple[dict, dict]:
        self.assert_current()
        params: dict = {"includeLayers": True}
        if self.path:
            params["cwd"] = str(self.path)
        config = await self.codex.request("config/read", params)
        requirements = await self.codex.request("configRequirements/read", {})
        self.assert_current()
        self.effective = assert_security_requirements(config, requirements, self.profile)
        LOGGER.info(
            "Generation config inspected generation=%s profile=%s layers=%s mcp_count=%s",
            self.epoch[0],
            self.profile,
            [(layer["name"]["type"], layer["version"]) for layer in config["layers"]],
            len(self.effective["mcp_servers"]),
        )
        return config, requirements

    async def inspect(self) -> None:
        self.snapshot = await self.read()

    async def recheck(self) -> None:
        require(self.snapshot is not None, "inspection_missing")
        self.assert_current()
        if self.thread_id:
            await assert_runtime(self.codex, self.thread_id, self.effective)
        require(await self.read() == self.snapshot, "configuration_changed")
        self.assert_current()

    async def start_thread(self) -> str:
        from backend.app.codex.policy import DEVELOPER_INSTRUCTIONS

        require(self.path is not None, "repository_missing")
        await self.inspect()
        config = generation_thread_config(self.job_id, self.effective)
        result = await self.codex.request(
            "thread/start",
            {
                "cwd": str(self.path),
                "ephemeral": True,
                "approvalPolicy": "never",
                "config": config,
                "developerInstructions": DEVELOPER_INSTRUCTIONS,
            },
        )
        # Retain even a malformed response's ID so the caller can unsubscribe.
        self.thread_id = result.get("thread", {}).get("id")
        self.assert_current()
        thread_id = assert_thread(result, self.path, self.profile)
        await self.recheck()
        return thread_id
