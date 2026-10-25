from __future__ import annotations

from copy import deepcopy
from uuid import UUID


class GenerationSecurityError(RuntimeError):
    pass


def permission_profile_name(job_id: UUID) -> str:
    return f"repospec_generation_{job_id.hex}"


def generation_thread_config(
    job_id: UUID,
    effective_config: dict[str, object],
) -> dict[str, object]:
    _assert_no_legacy_sandbox(effective_config)
    profile = permission_profile_name(job_id)
    config: dict[str, object] = {
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
        "apps": {"_default": {"enabled": False}},
    }
    apps = effective_config.get("apps")
    if isinstance(apps, dict):
        for name in apps:
            if name != "_default":
                config["apps"][name] = {"enabled": False}  # type: ignore[index]
    servers = effective_config.get("mcp_servers")
    if not isinstance(servers, dict):
        raise GenerationSecurityError("MCP server inventory is unavailable")
    config["mcp_servers"] = {name: {"enabled": False} for name in servers}
    return config


def assert_security_requirements(
    config_read: dict[str, object],
    requirements_read: dict[str, object],
) -> dict[str, object]:
    effective = config_read.get("config")
    if not isinstance(effective, dict):
        raise GenerationSecurityError("Effective Codex configuration is unavailable")
    _assert_no_legacy_sandbox(effective)
    if "requirements" not in requirements_read:
        raise GenerationSecurityError("Managed configuration requirements are unavailable")
    requirements = requirements_read.get("requirements")
    if requirements not in (None, {}):
        serialized = repr(requirements).lower()
        if "permission" in serialized or "config" in serialized:
            raise GenerationSecurityError("Managed requirements may reject the permission profile")
    return deepcopy(effective)


def plugin_ids(plugin_list: dict[str, object]) -> list[str]:
    if plugin_list.get("marketplaceLoadErrors"):
        raise GenerationSecurityError("Plugin marketplace inventory contains load errors")
    marketplaces = plugin_list.get("marketplaces")
    if isinstance(marketplaces, list):
        candidates: list[object] = []
        for marketplace in marketplaces:
            if not isinstance(marketplace, dict) or not isinstance(
                marketplace.get("plugins"), list
            ):
                raise GenerationSecurityError("Plugin inventory is invalid")
            candidates.extend(marketplace["plugins"])
    else:
        # Compatibility seam for older/fake App Server fixtures.
        candidates = plugin_list.get("data", plugin_list.get("plugins"))  # type: ignore[assignment]
    if not isinstance(candidates, list):
        raise GenerationSecurityError("Plugin inventory is unavailable")
    result: list[str] = []
    for item in candidates:
        if not isinstance(item, dict):
            raise GenerationSecurityError("Plugin inventory is invalid")
        plugin_id = item.get("id") or item.get("pluginId")
        if not isinstance(plugin_id, str) or not plugin_id:
            raise GenerationSecurityError("Plugin inventory contains an invalid id")
        result.append(plugin_id)
    return list(dict.fromkeys(result))


def _assert_no_legacy_sandbox(config: dict[str, object]) -> None:
    for key in ("sandbox_mode", "sandbox_workspace_write"):
        if config.get(key) is not None:
            raise GenerationSecurityError("Legacy sandbox configuration is active")
