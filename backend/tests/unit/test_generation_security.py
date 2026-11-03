from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.codex.policy import DISABLED_FEATURES
from backend.app.generation.security import (
    GenerationPreflight,
    GenerationSecurityError,
    assert_runtime,
    assert_security_requirements,
    assert_thread,
    generation_thread_config,
    permission_profile_name,
)
from backend.tests.fixtures.security_config import config_read
from backend.tests.integration.test_generation_api import StructuredCodex


def test_canonical_profile_and_explicit_tool_overrides():
    job_id = uuid4()
    config = generation_thread_config(job_id, config_read()["config"])
    profile = permission_profile_name(job_id)
    assert config["permissions"][profile]["filesystem"] == {
        ":root": "deny",
        ":minimal": "read",
        ":workspace_roots": {".": "read"},
    }
    assert config["permissions"][profile]["network"] == {"enabled": False}
    assert config["mcp_servers"] == {"external": {"enabled": False}}
    with pytest.raises(GenerationSecurityError, match="collision"):
        generation_thread_config(job_id, {**config_read()["config"], "permissions": {profile: {}}})


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("sandbox_mode", "read-only"),
        ("developer_instructions", "secret instruction"),
        ("mcp_servers", None),
        ("features", {}),
        ("web_search", "live"),
        ("shell_environment_policy", {"inherit": "all"}),
        ("permissions", {"other": {"extends": "wide"}}),
        ("permissions", {"other": {"filesystem": {"/outside": "read"}}}),
        ("new_permissions_setting", True),
    ],
)
def test_unsafe_effective_config(key, value):
    response = config_read()
    response["config"][key] = value
    with pytest.raises(GenerationSecurityError):
        assert_security_requirements(response, {"requirements": None})


def test_merged_secret_and_active_layers_are_rejected():
    response = config_read()
    response["config"]["shell_environment_policy"]["set"]["SECRET"] = "sensitive"
    with pytest.raises(GenerationSecurityError, match="merge"):
        assert_security_requirements(response, {"requirements": None})
    response = config_read()
    layer = response["layers"][0]
    layer["config"] = {"sandbox_mode": "danger-full-access"}
    with pytest.raises(GenerationSecurityError, match="legacy"):
        assert_security_requirements(response, {"requirements": None})
    layer["disabledReason"] = "untrusted"
    assert_security_requirements(response, {"requirements": None})


@pytest.mark.parametrize(
    "requirements",
    [
        {},
        {"requirements": {"allowedApprovalPolicies": ["on-request"]}},
        {"requirements": {"allowedWebSearchModes": []}},
        {"requirements": {"featureRequirements": {"plugins": True}}},
        {"requirements": {"allowedPermissionProfiles": {}}},
        {"requirements": {"defaultPermissions": "other"}},
        {"requirements": {"network": {"enabled": True}}},
        {"requirements": {"unknown": False}},
    ],
)
def test_managed_requirements_fail_closed(requirements):
    with pytest.raises(GenerationSecurityError):
        assert_security_requirements(config_read(), requirements)


def test_supported_managed_constraints_and_missing_layers():
    assert_security_requirements(
        config_read(),
        {
            "requirements": {
                "allowedApprovalPolicies": ["never"],
                "allowedWebSearchModes": ["disabled"],
                "featureRequirements": dict.fromkeys(DISABLED_FEATURES, False),
            }
        },
    )
    with pytest.raises(GenerationSecurityError, match="layers"):
        assert_security_requirements({"config": {}, "origins": {}}, {"requirements": None})


@pytest.mark.asyncio
async def test_preflight_rechecks_config_and_connection(tmp_path: Path):
    codex = StructuredCodex({})
    check = GenerationPreflight(codex, uuid4(), tmp_path)
    await check.start_thread()
    assert check.thread_id
    assert set(codex.thread_params) == {
        "cwd",
        "ephemeral",
        "approvalPolicy",
        "config",
        "developerInstructions",
    }
    codex.security_epoch += 1
    with pytest.raises(GenerationSecurityError, match="expired"):
        await check.recheck()


@pytest.mark.asyncio
async def test_layer_change_before_turn(tmp_path: Path):
    codex = StructuredCodex({})
    check = GenerationPreflight(codex, uuid4(), tmp_path)
    await check.start_thread()
    check.snapshot = deepcopy(check.snapshot)
    check.snapshot[0]["layers"][0]["version"] = "changed"
    with pytest.raises(GenerationSecurityError, match="changed"):
        await check.recheck()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["missing", "duplicate", "enabled", "cursor", "mcp", "unknown"])
async def test_runtime_inventory_fails_closed(mode):
    codex = StructuredCodex({})
    original = codex.request

    async def request(method, params):
        result = await original(method, params)
        if method == "experimentalFeature/list":
            if mode == "missing":
                result["data"].pop()
            if mode == "duplicate":
                result["data"].append(result["data"][0])
            if mode == "enabled":
                result["data"][0]["enabled"] = True
            if mode == "cursor":
                result["nextCursor"] = "same"
        if method == "mcpServerStatus/list":
            if mode == "mcp":
                result["data"][0]["runtimeStatus"] = "notStarted"
            if mode == "unknown":
                result["data"][0]["name"] = "unexpected"
        return result

    codex.request = request
    with pytest.raises(GenerationSecurityError):
        await assert_runtime(codex, "thread", config_read()["config"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("cwd", "/wrong"),
        ("runtimeWorkspaceRoots", []),
        ("instructionSources", ["AGENTS.md"]),
        ("approvalPolicy", "on-request"),
        ("activePermissionProfile", {"id": "p", "extends": "broad"}),
    ],
)
def test_thread_provenance_required(field, value):
    result = {
        "cwd": "/fixture",
        "runtimeWorkspaceRoots": ["/fixture"],
        "instructionSources": [],
        "approvalPolicy": "never",
        "activePermissionProfile": {"id": "p", "extends": None},
        "thread": {"id": "t"},
    }
    result[field] = value
    with pytest.raises(GenerationSecurityError):
        assert_thread(result, Path("/fixture"), "p")


@pytest.mark.asyncio
async def test_all_inventory_pages_are_checked():
    codex = StructuredCodex({})
    original = codex.request
    calls = []

    async def request(method, params):
        calls.append((method, params))
        result = await original(method, params)
        if method == "experimentalFeature/list":
            rows = result["data"]
            result = {
                "data": rows[:4] if params["cursor"] is None else rows[4:],
                "nextCursor": "page-two" if params["cursor"] is None else None,
            }
        return result

    codex.request = request
    await assert_runtime(codex, "thread", config_read()["config"])
    assert any(params.get("cursor") == "page-two" for _, params in calls)


@pytest.mark.asyncio
async def test_connection_generation_and_account_changes_invalidate_inspection(tmp_path):
    codex = StructuredCodex({})
    for attribute in ("generation", "security_epoch", "rejection_count"):
        check = GenerationPreflight(codex, uuid4(), tmp_path)
        await check.start_thread()
        setattr(codex, attribute, getattr(codex, attribute) + 1)
        with pytest.raises(GenerationSecurityError):
            await check.recheck()
