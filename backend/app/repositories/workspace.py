from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID


class UnsafeWorkspaceError(RuntimeError):
    pass


class WorkspaceResolver:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.repositories_root = self.root / "repositories"
        self.staging_root = self.root / "staging"
        self.empty_hooks = self.root / "empty-hooks"
        self.empty_gitconfig = self.root / "empty-gitconfig"

    def prepare(self) -> None:
        if self.root.exists() and (self.root.is_symlink() or not self.root.is_dir()):
            raise UnsafeWorkspaceError("Workspace root is not a safe directory")
        for path in (self.root, self.repositories_root, self.staging_root, self.empty_hooks):
            path.mkdir(parents=True, exist_ok=True)
            self._assert_direct_child_or_root(path)
        self.empty_gitconfig.touch(exist_ok=True)

    def repository_path(self, workspace_key: str) -> Path:
        if str(UUID(workspace_key)) != workspace_key:
            raise UnsafeWorkspaceError("Invalid workspace key")
        path = self.repositories_root / workspace_key
        self._assert_child(path, self.repositories_root)
        return path

    def staging_path(self, operation_id: UUID) -> Path:
        path = self.staging_root / str(operation_id)
        self._assert_child(path, self.staging_root)
        return path

    def is_valid_repository(self, workspace_key: str) -> bool:
        try:
            path = self.repository_path(workspace_key)
        except (ValueError, UnsafeWorkspaceError):
            return False
        return path.is_dir() and not path.is_symlink() and (path / ".git").is_dir()

    def remove_invalid_repository(self, workspace_key: str) -> None:
        path = self.repository_path(workspace_key)
        if path.exists() and not self.is_valid_repository(workspace_key):
            if path.is_symlink() or not path.is_dir():
                raise UnsafeWorkspaceError("Invalid managed repository path")
            shutil.rmtree(path)

    def _assert_direct_child_or_root(self, path: Path) -> None:
        resolved = path.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise UnsafeWorkspaceError("Workspace path escaped the managed root")

    @staticmethod
    def _assert_child(path: Path, parent: Path) -> None:
        resolved_parent = parent.resolve()
        resolved = path.resolve(strict=False)
        if resolved.parent != resolved_parent:
            raise UnsafeWorkspaceError("Workspace path escaped its managed directory")
