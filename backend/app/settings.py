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
    log_level: str = "INFO"

    @field_validator("test_chat_workspace")
    @classmethod
    def normalize_workspace(cls, value: Path) -> Path:
        path = value.expanduser().resolve()
        if not path.is_dir():
            raise ValueError("TEST_CHAT_WORKSPACE must be an existing directory")
        return path


settings = Settings()
