from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.repositories.workspace import UnsafeWorkspaceError, WorkspaceResolver
from backend.app.settings import Settings


def test_workspace_uses_only_generated_uuid(tmp_path: Path) -> None:
    workspace = WorkspaceResolver(tmp_path / "managed")
    workspace.prepare()
    repository_id = uuid4()

    assert workspace.repository_path(str(repository_id)) == (
        tmp_path / "managed" / "repositories" / str(repository_id)
    )
    assert workspace.staging_path(repository_id) == (
        tmp_path / "managed" / "staging" / str(repository_id)
    )

    with pytest.raises((ValueError, UnsafeWorkspaceError)):
        workspace.repository_path("../outside")


def test_workspace_rejects_symlink_root(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(actual, target_is_directory=True)
    with pytest.raises(ValueError, match="must not be a symlink"):
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            workspace_root=linked,
            test_chat_workspace=tmp_path,
        )


def test_delete_repository_removes_only_managed_uuid_directory(tmp_path: Path) -> None:
    workspace = WorkspaceResolver(tmp_path / "managed")
    workspace.prepare()
    repository_id = uuid4()
    repository_path = workspace.repository_path(str(repository_id))
    repository_path.mkdir()
    (repository_path / "source.py").write_text("print('safe')\n")

    workspace.delete_repository(str(repository_id))
    assert not repository_path.exists()
    workspace.delete_repository(str(repository_id))

    with pytest.raises((ValueError, UnsafeWorkspaceError)):
        workspace.delete_repository("../outside")


def test_delete_repository_rejects_symlink(tmp_path: Path) -> None:
    workspace = WorkspaceResolver(tmp_path / "managed")
    workspace.prepare()
    outside = tmp_path / "outside"
    outside.mkdir()
    repository_id = uuid4()
    workspace.repositories_root.joinpath(str(repository_id)).symlink_to(
        outside, target_is_directory=True
    )

    with pytest.raises(UnsafeWorkspaceError):
        workspace.delete_repository(str(repository_id))
    assert outside.is_dir()
