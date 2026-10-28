from uuid import uuid4

import pytest

from backend.app.generation.security import (
    GenerationSecurityError,
    assert_security_requirements,
    generation_thread_config,
    permission_profile_name,
    plugin_ids,
)


def test_job_specific_permission_profile_and_external_tool_overrides() -> None:
    job_id = uuid4()
    effective = {
        "sandbox_mode": None,
        "sandbox_workspace_write": None,
        "apps": {"drive": {"enabled": True}},
        "mcp_servers": {"docs": {"enabled": True}, "browser": {"enabled": True}},
    }
    config = generation_thread_config(job_id, effective)
    profile = permission_profile_name(job_id)
    assert profile == f"repospec_generation_{job_id.hex}"
    assert config["default_permissions"] == profile
    permissions = config["permissions"][profile]  # type: ignore[index]
    assert permissions["filesystem"] == {  # type: ignore[index]
        ":root": "deny",
        ":minimal": "read",
        ":workspace_roots": {".": "read"},
    }
    assert permissions["network"] == {"enabled": False}  # type: ignore[index]
    assert config["web_search"] == "disabled"
    assert config["apps"] == {"_default": {"enabled": False}, "drive": {"enabled": False}}
    assert config["mcp_servers"] == {"docs": {"enabled": False}, "browser": {"enabled": False}}


def test_security_gate_fails_closed() -> None:
    with pytest.raises(GenerationSecurityError, match="Legacy"):
        assert_security_requirements(
            {"config": {"sandbox_mode": "read-only"}}, {"requirements": None}
        )
    with pytest.raises(GenerationSecurityError, match="inventory"):
        plugin_ids({})
    with pytest.raises(GenerationSecurityError, match="requirements"):
        assert_security_requirements({"config": {}}, {})


def test_plugin_inventory_requires_ids() -> None:
    assert plugin_ids({"data": [{"id": "one"}, {"pluginId": "two"}]}) == ["one", "two"]
    assert plugin_ids(
        {
            "marketplaces": [{"name": "local", "plugins": [{"id": "one"}, {"id": "two"}]}],
            "marketplaceLoadErrors": [],
        }
    ) == ["one", "two"]
