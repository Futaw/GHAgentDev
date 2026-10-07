from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError

from backend.app.repositories.git import GitClient, GitOperationError
from backend.app.repositories.models import RepositoryModel, RepositoryStatus
from backend.app.repositories.store import DuplicateRepositoryError, RepositoryStore
from backend.app.repositories.url import GitHubRepositoryUrl, normalize_github_url
from backend.app.repositories.workspace import UnsafeWorkspaceError, WorkspaceResolver

LOGGER = logging.getLogger(__name__)


class RepositoryNotFoundError(RuntimeError):
    pass


class RepositoryBusyError(RuntimeError):
    pass


class RepositoryInUseError(RuntimeError):
    pass


class RepositoryDeleteError(RuntimeError):
    pass


class RepositoryAlreadyRegisteredError(RuntimeError):
    def __init__(self, repository_id: UUID | None) -> None:
        super().__init__("このRepositoryは登録済みです。")
        self.repository_id = repository_id


class DatabaseUnavailableError(RuntimeError):
    pass


class RepositoryOperationRunner:
    def __init__(self) -> None:
        self._locks: dict[UUID, asyncio.Lock] = {}
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._stopping = False

    def schedule(self, repository_id: UUID, operation: Callable[[], Awaitable[None]]) -> None:
        if self._stopping:
            raise RuntimeError("Repository operations are stopping")
        current = self._tasks.get(repository_id)
        lock = self._locks.setdefault(repository_id, asyncio.Lock())
        if lock.locked() or (current and not current.done()):
            raise RepositoryBusyError("Repositoryの処理はすでに実行中です。")
        task = asyncio.create_task(self._run(repository_id, operation))
        self._tasks[repository_id] = task
        task.add_done_callback(lambda completed: self._task_done(repository_id, completed))

    @asynccontextmanager
    async def exclusive(self, repository_id: UUID) -> AsyncIterator[None]:
        if self._stopping:
            raise RepositoryBusyError("Repositoryの処理を開始できません。")
        current = self._tasks.get(repository_id)
        lock = self._locks.setdefault(repository_id, asyncio.Lock())
        if lock.locked() or (current and not current.done()):
            raise RepositoryBusyError("Repositoryの処理はすでに実行中です。")
        await lock.acquire()
        try:
            current = self._tasks.get(repository_id)
            if current and not current.done():
                raise RepositoryBusyError("Repositoryの処理はすでに実行中です。")
            yield
        finally:
            lock.release()

    async def _run(self, repository_id: UUID, operation: Callable[[], Awaitable[None]]) -> None:
        lock = self._locks.setdefault(repository_id, asyncio.Lock())
        async with lock:
            await operation()

    def _task_done(self, repository_id: UUID, task: asyncio.Task[None]) -> None:
        if self._tasks.get(repository_id) is task:
            self._tasks.pop(repository_id, None)
        if not task.cancelled() and (error := task.exception()):
            LOGGER.error(
                "Repository operation failed: %s",
                type(error).__name__,
                extra={"repository_id": str(repository_id)},
            )

    async def shutdown(self) -> None:
        self._stopping = True
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()


class RepositoryService:
    def __init__(
        self,
        store: RepositoryStore,
        git: GitClient,
        workspace: WorkspaceResolver,
        runner: RepositoryOperationRunner,
    ) -> None:
        self.store = store
        self.git = git
        self.workspace = workspace
        self.runner = runner

    async def create(self, raw_url: str) -> RepositoryModel:
        parsed = normalize_github_url(raw_url)
        repository_id = uuid4()
        now = datetime.now(UTC)
        model = RepositoryModel(
            id=repository_id,
            owner=parsed.owner,
            name=parsed.name,
            canonical_github_url=parsed.canonical_url,
            workspace_key=str(repository_id),
            default_branch=None,
            latest_commit_sha=None,
            status=RepositoryStatus.PENDING.value,
            last_synced_at=None,
            last_error_code=None,
            last_error_message=None,
            created_at=now,
            updated_at=now,
        )
        try:
            await self.store.create(model)
        except DuplicateRepositoryError as exc:
            raise RepositoryAlreadyRegisteredError(exc.repository_id) from exc
        except SQLAlchemyError as exc:
            raise DatabaseUnavailableError from exc
        try:
            self.runner.schedule(repository_id, lambda: self._clone(repository_id, parsed, True))
        except Exception as exc:
            await self.store.mark_failed(
                repository_id,
                "OPERATION_INTERRUPTED",
                "処理を開始できませんでした。再試行してください。",
            )
            raise RepositoryBusyError("Repositoryの処理を開始できませんでした。") from exc
        return model

    async def list(self) -> list[RepositoryModel]:
        try:
            return await self.store.list()
        except SQLAlchemyError as exc:
            raise DatabaseUnavailableError from exc

    async def get(self, repository_id: UUID) -> RepositoryModel:
        try:
            model = await self.store.get(repository_id)
        except SQLAlchemyError as exc:
            raise DatabaseUnavailableError from exc
        if model is None:
            raise RepositoryNotFoundError("Repositoryが見つかりません。")
        return model

    async def start_sync(self, repository_id: UUID) -> RepositoryModel:
        model = await self.get(repository_id)
        if model.status not in {RepositoryStatus.READY.value, RepositoryStatus.FAILED.value}:
            raise RepositoryBusyError("Repositoryの処理はすでに実行中です。")
        has_workspace = self.workspace.is_valid_repository(model.workspace_key)
        new_status = RepositoryStatus.SYNCING if has_workspace else RepositoryStatus.CLONING
        try:
            updated = await self.store.begin_operation(
                repository_id,
                {RepositoryStatus.READY, RepositoryStatus.FAILED},
                new_status,
            )
        except SQLAlchemyError as exc:
            raise DatabaseUnavailableError from exc
        if updated is None:
            raise RepositoryBusyError("Repositoryの処理はすでに実行中です。")
        parsed = GitHubRepositoryUrl(model.owner, model.name, model.canonical_github_url)
        try:
            if has_workspace:
                self.runner.schedule(repository_id, lambda: self._sync(repository_id, model))
            else:
                self.runner.schedule(
                    repository_id, lambda: self._clone(repository_id, parsed, False)
                )
        except Exception as exc:
            await self.store.mark_failed(
                repository_id,
                "OPERATION_INTERRUPTED",
                "処理を開始できませんでした。再試行してください。",
            )
            raise RepositoryBusyError("Repositoryの処理を開始できませんでした。") from exc
        return updated

    async def recover_interrupted(self) -> int:
        try:
            return await self.store.recover_interrupted()
        except SQLAlchemyError as exc:
            raise DatabaseUnavailableError from exc

    async def delete(self, repository_id: UUID, trace_id: str) -> None:
        model = await self.get(repository_id)
        self._ensure_deletable(model)
        async with self.runner.exclusive(repository_id):
            model = await self.get(repository_id)
            self._ensure_deletable(model)
            try:
                if await self.store.has_related_data(repository_id):
                    raise RepositoryInUseError("関連するViewerなどを先に削除してください。")
            except SQLAlchemyError as exc:
                raise DatabaseUnavailableError from exc

            self._log_delete("repository.workspace_delete_started", repository_id, trace_id)
            try:
                await asyncio.to_thread(
                    self.workspace.delete_repository,
                    model.workspace_key,
                )
            except (OSError, UnsafeWorkspaceError) as exc:
                self._log_delete(
                    "repository.workspace_delete_failed",
                    repository_id,
                    trace_id,
                    logging.ERROR,
                )
                raise RepositoryDeleteError(
                    "管理Workspaceを削除できませんでした。再試行してください。"
                ) from exc
            self._log_delete("repository.workspace_delete_completed", repository_id, trace_id)

            self._log_delete("repository.record_delete_started", repository_id, trace_id)
            try:
                deleted = await self.store.delete(repository_id)
            except SQLAlchemyError as exc:
                self._log_delete(
                    "repository.record_delete_failed",
                    repository_id,
                    trace_id,
                    logging.ERROR,
                )
                raise DatabaseUnavailableError from exc
            if not deleted:
                self._log_delete(
                    "repository.record_delete_failed",
                    repository_id,
                    trace_id,
                    logging.ERROR,
                )
                raise RepositoryNotFoundError("Repositoryが見つかりません。")
            self._log_delete("repository.record_delete_completed", repository_id, trace_id)

    @staticmethod
    def _ensure_deletable(model: RepositoryModel) -> None:
        if model.status not in {RepositoryStatus.READY.value, RepositoryStatus.FAILED.value}:
            raise RepositoryBusyError("Repositoryの処理中は削除できません。")

    @staticmethod
    def _log_delete(
        event: str,
        repository_id: UUID,
        trace_id: str,
        level: int = logging.INFO,
    ) -> None:
        LOGGER.log(
            level,
            event,
            extra={"repository_id": str(repository_id), "trace_id": trace_id},
        )

    async def _clone(
        self,
        repository_id: UUID,
        parsed: GitHubRepositoryUrl,
        begin: bool,
    ) -> None:
        if begin:
            started = await self.store.begin_operation(
                repository_id, {RepositoryStatus.PENDING}, RepositoryStatus.CLONING
            )
            if started is None:
                return
        model = await self.store.get(repository_id)
        if model is None:
            return
        operation_id = uuid4()
        try:
            self.workspace.remove_invalid_repository(model.workspace_key)
            metadata = await self.git.clone(
                parsed.canonical_url,
                self.workspace.staging_path(operation_id),
                self.workspace.repository_path(model.workspace_key),
            )
            await self.store.mark_ready(repository_id, metadata.default_branch, metadata.commit_sha)
        except asyncio.CancelledError:
            await self.store.mark_failed(
                repository_id, "OPERATION_INTERRUPTED", "処理が中断されました。再試行してください。"
            )
            raise
        except GitOperationError as exc:
            code = "REPOSITORY_TOO_LARGE" if exc.code == "REPOSITORY_TOO_LARGE" else "CLONE_FAILED"
            message = (
                str(exc)
                if code == "REPOSITORY_TOO_LARGE"
                else (
                    "Public Repositoryへアクセスできませんでした。URLと公開状態を確認してください。"
                )
            )
            await self.store.mark_failed(repository_id, code, message)
        except Exception:
            LOGGER.exception(
                "Unexpected clone failure", extra={"repository_id": str(repository_id)}
            )
            await self.store.mark_failed(
                repository_id, "CLONE_FAILED", "Repositoryを取得できませんでした。"
            )

    async def _sync(self, repository_id: UUID, model: RepositoryModel) -> None:
        try:
            metadata = await self.git.sync(
                self.workspace.repository_path(model.workspace_key), model.canonical_github_url
            )
            await self.store.mark_ready(repository_id, metadata.default_branch, metadata.commit_sha)
        except asyncio.CancelledError:
            await self.store.mark_failed(
                repository_id, "OPERATION_INTERRUPTED", "処理が中断されました。再試行してください。"
            )
            raise
        except GitOperationError as exc:
            code = "REPOSITORY_TOO_LARGE" if exc.code == "REPOSITORY_TOO_LARGE" else "SYNC_FAILED"
            message = (
                str(exc) if code == "REPOSITORY_TOO_LARGE" else "最新コードを取得できませんでした。"
            )
            await self.store.mark_failed(repository_id, code, message)
        except Exception:
            LOGGER.exception("Unexpected sync failure", extra={"repository_id": str(repository_id)})
            await self.store.mark_failed(
                repository_id, "SYNC_FAILED", "最新コードを取得できませんでした。"
            )
