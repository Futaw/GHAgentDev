from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from backend.app.repositories.url import InvalidGitHubUrlError, normalize_github_url
from backend.app.repositories.workspace import WorkspaceResolver


class GitOperationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class GitMetadata:
    default_branch: str
    commit_sha: str


class GitClient:
    _OUTPUT_LIMIT = 16 * 1024 * 1024

    def __init__(
        self,
        executable: str,
        workspace: WorkspaceResolver,
        clone_timeout_seconds: float,
        sync_timeout_seconds: float,
        max_repository_bytes: int,
        max_file_count: int,
        *,
        allow_local_sources_for_tests: bool = False,
    ) -> None:
        self.executable = executable
        self.workspace = workspace
        self.clone_timeout_seconds = clone_timeout_seconds
        self.sync_timeout_seconds = sync_timeout_seconds
        self.max_repository_bytes = max_repository_bytes
        self.max_file_count = max_file_count
        self.allow_local_sources_for_tests = allow_local_sources_for_tests

    async def clone(self, source: str, staging: Path, destination: Path) -> GitMetadata:
        self._assert_managed_staging(staging)
        self._assert_managed_repository(destination)
        if await asyncio.to_thread(self._clone_paths_exist, staging, destination):
            raise GitOperationError("CLONE_FAILED", "Repositoryの作業領域を準備できませんでした。")
        try:
            await self._run(
                [
                    *self._safe_options(),
                    "clone",
                    "--no-tags",
                    "--origin",
                    "origin",
                    "--",
                    source,
                    str(staging),
                ],
                self.clone_timeout_seconds,
            )
            metadata = await self._validate(staging, source)
            await asyncio.to_thread(destination.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(staging.rename, destination)
            return metadata
        except GitOperationError:
            await asyncio.to_thread(self._remove_staging, staging)
            raise
        except (OSError, ValueError) as exc:
            await asyncio.to_thread(self._remove_staging, staging)
            raise GitOperationError(
                "CLONE_FAILED",
                "Public Repositoryへアクセスできませんでした。URLと公開状態を確認してください。",
            ) from exc

    async def sync(self, destination: Path, expected_url: str) -> GitMetadata:
        self._assert_managed_repository(destination)
        if not await asyncio.to_thread(self._is_git_repository, destination):
            raise GitOperationError("SYNC_FAILED", "Repositoryの作業領域を確認できませんでした。")
        try:
            await self._verify_origin(destination, expected_url)
            await self._run(
                ["-C", str(destination), *self._safe_options(), "fetch", "--no-tags", "origin"],
                self.sync_timeout_seconds,
            )
            await self._run(
                [
                    "-C",
                    str(destination),
                    *self._safe_options(),
                    "remote",
                    "set-head",
                    "origin",
                    "-a",
                ],
                self.sync_timeout_seconds,
            )
            default_branch = await self._default_branch(destination)
            await self._run(
                [
                    "-C",
                    str(destination),
                    "reset",
                    "--hard",
                    f"refs/remotes/origin/{default_branch}",
                ],
                self.sync_timeout_seconds,
            )
            await self._run(
                [
                    "-C",
                    str(destination),
                    "-c",
                    f"core.hooksPath={self.workspace.empty_hooks}",
                    "clean",
                    "-ffdx",
                ],
                self.sync_timeout_seconds,
            )
            await self._check_limits(destination)
            return GitMetadata(default_branch, await self._commit_sha(destination))
        except GitOperationError:
            raise
        except (OSError, ValueError) as exc:
            raise GitOperationError("SYNC_FAILED", "最新コードを取得できませんでした。") from exc

    async def _validate(self, path: Path, expected_url: str) -> GitMetadata:
        if not await asyncio.to_thread(self._is_git_repository, path):
            raise GitOperationError("CLONE_FAILED", "取得したRepositoryを検証できませんでした。")
        await self._verify_origin(path, expected_url)
        await self._check_limits(path)
        return GitMetadata(await self._default_branch(path), await self._commit_sha(path))

    async def _verify_origin(self, path: Path, expected_url: str) -> None:
        origin = (
            await self._run(
                ["-C", str(path), "remote", "get-url", "origin"], self.sync_timeout_seconds
            )
        ).strip()
        try:
            if (
                normalize_github_url(origin).canonical_url
                != normalize_github_url(expected_url).canonical_url
            ):
                raise GitOperationError("SYNC_FAILED", "Repositoryの接続先を検証できませんでした。")
        except InvalidGitHubUrlError as exc:
            # Local paths are allowed only as an explicit test seam.
            if not self.allow_local_sources_for_tests:
                raise GitOperationError(
                    "SYNC_FAILED", "Repositoryの接続先を検証できませんでした。"
                ) from exc
            paths_match = await asyncio.to_thread(self._local_paths_match, origin, expected_url)
            if not paths_match:
                raise GitOperationError(
                    "SYNC_FAILED", "Repositoryの接続先を検証できませんでした。"
                ) from exc

    async def _default_branch(self, path: Path) -> str:
        ref = (
            await self._run(
                ["-C", str(path), "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
                self.sync_timeout_seconds,
            )
        ).strip()
        prefix = "origin/"
        if not ref.startswith(prefix) or len(ref) == len(prefix):
            raise GitOperationError("SYNC_FAILED", "Default Branchを確認できませんでした。")
        return ref[len(prefix) :]

    async def _commit_sha(self, path: Path) -> str:
        sha = (
            await self._run(["-C", str(path), "rev-parse", "HEAD"], self.sync_timeout_seconds)
        ).strip()
        if len(sha) != 40 or any(character not in "0123456789abcdef" for character in sha.lower()):
            raise GitOperationError("SYNC_FAILED", "Commitを確認できませんでした。")
        return sha

    async def _check_limits(self, path: Path) -> None:
        total = await asyncio.to_thread(self._directory_size, path)
        if total > self.max_repository_bytes:
            raise GitOperationError(
                "REPOSITORY_TOO_LARGE", "Repositoryの容量が上限を超えています。"
            )
        files = await self._run(["-C", str(path), "ls-files", "-z"], self.sync_timeout_seconds)
        count = len([item for item in files.split("\0") if item])
        if count > self.max_file_count:
            raise GitOperationError(
                "REPOSITORY_TOO_LARGE", "Repositoryのファイル数が上限を超えています。"
            )

    def _directory_size(self, path: Path) -> int:
        total = 0
        pending = [path]
        while pending:
            current = pending.pop()
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                        if total > self.max_repository_bytes:
                            return total
        return total

    async def _run(self, arguments: list[str], deadline_seconds: float) -> str:
        environment = os.environ.copy()
        for key in list(environment):
            if key.startswith("GIT_") or key in {"SSH_ASKPASS", "GIT_ASKPASS"}:
                environment.pop(key, None)
        environment.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_CONFIG_GLOBAL": str(self.workspace.empty_gitconfig),
                "GIT_CONFIG_SYSTEM": str(self.workspace.empty_gitconfig),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_ASKPASS": "",
                "SSH_ASKPASS": "",
            }
        )
        try:
            process = await asyncio.create_subprocess_exec(
                self.executable,
                *arguments,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=environment,
            )
            try:
                stdout_result, stderr_result, _ = await asyncio.wait_for(
                    asyncio.gather(
                        self._read_limited(process.stdout, process),
                        self._read_limited(process.stderr, process),
                        process.wait(),
                    ),
                    timeout=deadline_seconds,
                )
            except TimeoutError as exc:
                await self._stop_process(process)
                raise GitOperationError("SYNC_FAILED", "Git処理がタイムアウトしました。") from exc
            except asyncio.CancelledError:
                await self._stop_process(process)
                raise
        except OSError as exc:
            raise GitOperationError("SYNC_FAILED", "Gitを実行できませんでした。") from exc
        stdout, stdout_too_large = stdout_result
        stderr, stderr_too_large = stderr_result
        if stdout_too_large or stderr_too_large:
            raise GitOperationError("REPOSITORY_TOO_LARGE", "Gitの出力が上限を超えました。")
        if process.returncode != 0:
            raise GitOperationError("SYNC_FAILED", "Git処理に失敗しました。")
        return stdout.decode("utf-8", errors="replace")

    async def _read_limited(
        self,
        stream: asyncio.StreamReader | None,
        process: asyncio.subprocess.Process,
    ) -> tuple[bytes, bool]:
        if stream is None:
            return b"", False
        chunks: list[bytes] = []
        total = 0
        too_large = False
        while chunk := await stream.read(64 * 1024):
            total += len(chunk)
            if total > self._OUTPUT_LIMIT:
                too_large = True
                if process.returncode is None:
                    process.kill()
            elif not too_large:
                chunks.append(chunk)
        return b"".join(chunks), too_large

    @staticmethod
    async def _stop_process(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=2)
        except TimeoutError:
            process.kill()
            await process.wait()

    def _safe_options(self) -> list[str]:
        return [
            "-c",
            "credential.helper=",
            "-c",
            f"core.hooksPath={self.workspace.empty_hooks}",
            "-c",
            (
                "protocol.file.allow=always"
                if self.allow_local_sources_for_tests
                else "protocol.file.allow=never"
            ),
            "-c",
            "http.followRedirects=false",
        ]

    @staticmethod
    def _clone_paths_exist(staging: Path, destination: Path) -> bool:
        return staging.exists() or destination.exists()

    @staticmethod
    def _is_git_repository(path: Path) -> bool:
        return path.is_dir() and (path / ".git").is_dir()

    @staticmethod
    def _local_paths_match(origin: str, expected_url: str) -> bool:
        return Path(origin).resolve() == Path(expected_url).resolve()

    def _assert_managed_staging(self, path: Path) -> None:
        if path.resolve(strict=False).parent != self.workspace.staging_root.resolve():
            raise GitOperationError("CLONE_FAILED", "Repositoryの作業領域が不正です。")

    def _assert_managed_repository(self, path: Path) -> None:
        if path.resolve(strict=False).parent != self.workspace.repositories_root.resolve():
            raise GitOperationError("SYNC_FAILED", "Repositoryの作業領域が不正です。")

    def _remove_staging(self, path: Path) -> None:
        self._assert_managed_staging(path)
        if path.exists() and not path.is_symlink():
            shutil.rmtree(path)
