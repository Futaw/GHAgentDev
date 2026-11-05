"""Non-sensitive config/read shape for the reviewed CLI (not a sandbox proof)."""

from backend.app.codex.policy import DISABLED_FEATURES, SAFE_PATH


def config_read():
    return {
        "config": {
            "sandbox_mode": None,
            "sandbox_workspace_write": None,
            "features": dict.fromkeys(DISABLED_FEATURES, False),
            "web_search": "disabled",
            "allow_login_shell": False,
            "project_doc_max_bytes": 0,
            "shell_environment_policy": {
                "inherit": "none",
                "ignore_default_excludes": False,
                "set": {"PATH": SAFE_PATH},
                "include_only": ["PATH"],
            },
            "apps": None,
            "mcp_servers": {"external": {"enabled": True}},
        },
        "origins": {},
        "layers": [
            {
                "name": {"type": "sessionFlags"},
                "version": "sha256:fixture",
                "config": {},
                "disabledReason": None,
            }
        ],
    }
