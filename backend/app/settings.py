from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    codex_executable: str = "codex"
    codex_client_name: str = "repospec_viewer"
    codex_client_title: str = "RepoSpec Viewer"
    codex_client_version: str = "0.1.0"
    test_chat_workspace: Path = Field(default_factory=Path.cwd)
    codex_request_timeout_seconds: float = 30
    codex_restart_delay_seconds: float = 2
    sse_heartbeat_seconds: float = 20
    sse_event_buffer_size: int = 500
    database_url: str
    workspace_root: Path = Path(".data/workspaces")
    git_executable: str = "git"
    git_clone_timeout_seconds: float = 300
    git_sync_timeout_seconds: float = 120
    git_max_repository_bytes: int = 1_073_741_824
    git_max_file_count: int = 100_000
    log_level: str = "INFO"

    @field_validator("test_chat_workspace")
    @classmethod
    def normalize_workspace(cls, value: Path) -> Path:
        path = value.expanduser().resolve()
        if not path.is_dir():
            raise ValueError("TEST_CHAT_WORKSPACE must be an existing directory")
        return path

    @field_validator("workspace_root")
    @classmethod
    def normalize_managed_workspace(cls, value: Path) -> Path:
        expanded = value.expanduser()
        if expanded.is_symlink():
            raise ValueError("WORKSPACE_ROOT must be a directory and must not be a symlink")
        path = expanded.resolve()
        if path.exists() and not path.is_dir():
            raise ValueError("WORKSPACE_ROOT must be a directory and must not be a symlink")
        return path

    @field_validator(
        "git_clone_timeout_seconds",
        "git_sync_timeout_seconds",
        "git_max_repository_bytes",
        "git_max_file_count",
    )
    @classmethod
    def positive_git_limit(cls, value: float | int) -> float | int:
        if value <= 0:
            raise ValueError("Git limits and timeouts must be positive")
        return value
