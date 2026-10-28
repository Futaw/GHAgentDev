from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from backend.app.generation.models import (
    GenerationJobModel,
    GenerationOperation,
    GenerationStatus,
    ViewerModel,
)
from backend.app.generation.runner import GenerationRunner
from backend.app.generation.store import GenerationReservationError, GenerationStore
from backend.app.repositories.models import RepositoryStatus
from backend.app.repositories.service import RepositoryOperationRunner, RepositoryService
from backend.app.settings import Settings
from backend.app.viewers.git_refs import viewer_revision_ref
from backend.app.viewers.options import (
    DENSITIES,
    DETAIL_LEVELS,
    DOCUMENT_TYPES,
    TARGET_AUDIENCES,
    THEMES,
)

LOGGER = logging.getLogger(__name__)


class GenerationDisabledError(RuntimeError):
    pass


class ViewerNotFoundError(RuntimeError):
    pass


class GenerationJobNotFoundError(RuntimeError):
    pass


class GenerationAlreadyRunningError(RuntimeError):
    pass


class ViewerBusyError(RuntimeError):
    pass


class ViewerChangedError(RuntimeError):
    pass


class IdempotencyKeyReusedError(RuntimeError):
    pass


class InvalidViewerOptionError(RuntimeError):
    pass


class ViewerDeleteError(RuntimeError):
    pass


class GenerationService:
    def __init__(
        self,
        store: GenerationStore,
        repositories: RepositoryService,
        operation_runner: RepositoryOperationRunner,
        runner: GenerationRunner,
        settings: Settings,
    ) -> None:
        self.store = store
        self.repositories = repositories
        self.operation_runner = operation_runner
        self.runner = runner
        self.settings = settings

    async def list_viewers(self, repository_id: UUID) -> list[ViewerModel]:
        await self.repositories.get(repository_id)
        return await self.store.list_viewers(repository_id)

    async def get_viewer(self, viewer_id: UUID) -> ViewerModel:
        viewer = await self.store.get_viewer(viewer_id)
        if viewer is None:
            raise ViewerNotFoundError("Viewerが見つかりません。")
        return viewer

    async def get_job(self, job_id: UUID) -> GenerationJobModel:
        job = await self.store.get_job(job_id)
        if job is None:
            raise GenerationJobNotFoundError("Generation Jobが見つかりません。")
        return job

    async def create(
        self,
        repository_id: UUID,
        idempotency_key: str,
        payload: dict[str, object],
    ) -> GenerationJobModel:
        self._enabled()
        normalized = self._normalize_payload(payload)
        request_hash = _request_hash("create", repository_id, None, normalized)
        existing = await self._idempotent(repository_id, idempotency_key, request_hash)
        if existing:
            return existing
        repository = await self.repositories.get(repository_id)
        if repository.status != RepositoryStatus.READY.value or not repository.latest_commit_sha:
            raise GenerationAlreadyRunningError("Repositoryを現在利用できません。")
        if await self.store.has_active_job(repository_id):
            raise GenerationAlreadyRunningError("Viewer生成はすでに実行中です。")
        job = self._new_job(
            repository_id,
            idempotency_key,
            request_hash,
            normalized,
            commit_sha=repository.latest_commit_sha,
            operation=GenerationOperation.CREATE,
        )
        return await self._persist_and_schedule(
            job, repository.workspace_key, repository.canonical_github_url
        )

    async def regenerate(self, viewer_id: UUID, idempotency_key: str) -> GenerationJobModel:
        self._enabled()
        viewer = await self.get_viewer(viewer_id)
        payload = _viewer_payload(viewer)
        request_hash = _request_hash("regenerate", viewer.repository_id, viewer_id, payload)
        existing = await self._idempotent(viewer.repository_id, idempotency_key, request_hash)
        if existing:
            return existing
        repository = await self.repositories.get(viewer.repository_id)
        if repository.status != "ready" or not repository.latest_commit_sha:
            raise GenerationAlreadyRunningError("Repositoryを現在利用できません。")
        if await self.store.has_active_job(viewer.repository_id):
            raise GenerationAlreadyRunningError("Viewer生成はすでに実行中です。")
        job = self._new_job(
            viewer.repository_id,
            idempotency_key,
            request_hash,
            payload,
            commit_sha=repository.latest_commit_sha,
            operation=GenerationOperation.REGENERATE,
            viewer_id=viewer.id,
            base_revision=viewer.content_revision,
        )
        return await self._persist_and_schedule(
            job, repository.workspace_key, repository.canonical_github_url
        )

    async def retry(self, job_id: UUID, idempotency_key: str) -> GenerationJobModel:
        self._enabled()
        original = await self.get_job(job_id)
        if original.status not in {"cancelled", "failed"} or (
            original.status == "failed" and not original.error_retryable
        ):
            raise InvalidViewerOptionError("このJobは再試行できません。")
        if original.viewer_id and original.base_viewer_revision is not None:
            viewer = await self.get_viewer(original.viewer_id)
            if viewer.content_revision != original.base_viewer_revision:
                raise ViewerChangedError("Viewerは生成開始後に更新されました。")
        payload = {
            "request": original.request,
            "additional_instruction": original.additional_instruction,
            "document_type": original.document_type,
            "detail_level": original.detail_level,
            "target_audience": original.target_audience,
            "theme_slug": original.theme_slug,
            "density": original.density,
        }
        request_hash = _request_hash("retry", original.repository_id, original.id, payload)
        existing = await self._idempotent(original.repository_id, idempotency_key, request_hash)
        if existing:
            return existing
        repository = await self.repositories.get(original.repository_id)
        if repository.status != "ready" or await self.store.has_active_job(original.repository_id):
            raise GenerationAlreadyRunningError("Repositoryの別の処理が実行中です。")
        job = self._new_job(
            original.repository_id,
            idempotency_key,
            request_hash,
            payload,
            commit_sha=original.commit_sha,
            operation=GenerationOperation(original.operation),
            viewer_id=original.viewer_id,
            base_revision=original.base_viewer_revision,
            retry_of=original.id,
        )
        return await self._persist_and_schedule(
            job, repository.workspace_key, repository.canonical_github_url
        )

    async def cancel(self, job_id: UUID) -> GenerationJobModel:
        job = await self.store.request_cancel(job_id)
        if job is None:
            raise GenerationJobNotFoundError("Generation Jobが見つかりません。")
        if job.status == "cancelled":
            await self.runner.event_buffer(job.id).publish("job.cancelled", {"job_id": str(job.id)})
        elif job.status == "running":
            await self.runner.cancel(job)
        return job

    async def update_appearance(
        self, viewer_id: UUID, theme_slug: str | None, density: str | None
    ) -> ViewerModel:
        if theme_slug is None and density is None:
            raise InvalidViewerOptionError("ThemeまたはDensityを指定してください。")
        if theme_slug is not None and theme_slug not in THEMES:
            raise InvalidViewerOptionError("Themeが不正です。")
        if density is not None and density not in DENSITIES:
            raise InvalidViewerOptionError("Densityが不正です。")
        viewer = await self.store.update_appearance(viewer_id, theme_slug, density)
        if viewer is None:
            raise ViewerNotFoundError("Viewerが見つかりません。")
        return viewer

    async def delete(self, viewer_id: UUID) -> None:
        viewer = await self.get_viewer(viewer_id)
        if await self.store.has_active_viewer_job(viewer_id):
            raise ViewerBusyError("Viewerの再生成中は削除できません。")
        repository = await self.repositories.get(viewer.repository_id)
        path = self.repositories.workspace.repository_path(repository.workspace_key)
        try:
            await self.runner.refs.delete_viewer(str(path), viewer.id)
            if not await self.store.delete_viewer(viewer.id):
                raise ViewerNotFoundError("Viewerが見つかりません。")
        except ViewerNotFoundError:
            raise
        except Exception as exc:
            raise ViewerDeleteError("Viewerを削除できませんでした。") from exc

    async def recover_interrupted(self) -> int:
        ids = await self.store.recover_interrupted()
        for job_id in ids:
            job = await self.store.get_job(job_id)
            if job:
                repository = await self.repositories.get(job.repository_id)
                path = self.repositories.workspace.repository_path(repository.workspace_key)
                await self.runner.refs.delete(str(path), f"refs/repospec/generation/{job_id}")
        return len(ids)

    async def reconcile_refs(self) -> int:
        """Remove Generation and obsolete Viewer refs after DB recovery."""
        removed = 0
        for repository in await self.repositories.list():
            if not self.repositories.workspace.is_valid_repository(repository.workspace_key):
                continue
            viewers = await self.store.list_viewers(repository.id)
            expected = {
                viewer_revision_ref(viewer.id, viewer.content_revision) for viewer in viewers
            }
            path = self.repositories.workspace.repository_path(repository.workspace_key)
            try:
                stale = await self.runner.refs.reconcile(str(path), expected)
            except Exception as exc:
                LOGGER.warning(
                    "Viewer Git ref reconciliation failed: %s",
                    type(exc).__name__,
                    extra={"repository_id": str(repository.id)},
                )
                continue
            removed += len(stale)
        return removed

    def _enabled(self) -> None:
        if not self.settings.generation_enabled:
            raise GenerationDisabledError("security gateが未完了のためViewer生成は無効です。")

    async def _idempotent(
        self, repository_id: UUID, key: str, request_hash: str
    ) -> GenerationJobModel | None:
        existing = await self.store.get_idempotent_job(repository_id, key)
        if existing and existing.request_hash != request_hash:
            raise IdempotencyKeyReusedError("Idempotency-Keyは別の操作で使用済みです。")
        return existing

    async def _persist_and_schedule(
        self, job: GenerationJobModel, workspace_key: str, github_url: str
    ) -> GenerationJobModel:
        try:
            await self.store.create_job(job)
        except GenerationReservationError as exc:
            raise GenerationAlreadyRunningError("Repositoryの別の処理が実行中です。") from exc
        except IntegrityError as exc:
            existing = await self.store.get_idempotent_job(job.repository_id, job.idempotency_key)
            if existing and existing.request_hash == job.request_hash:
                return existing
            raise GenerationAlreadyRunningError("Viewer生成はすでに実行中です。") from exc
        path = self.repositories.workspace.repository_path(workspace_key)
        try:
            task = self.operation_runner.schedule(
                job.repository_id,
                lambda: self.runner.execute(job.id, path, github_url),
                gate=self.runner.semaphore,
                should_run=lambda: self.store.is_queued(job.id),
            )
            self.runner.tasks[job.id] = task
        except Exception as exc:
            await self.store.mark_terminal(
                job.id,
                GenerationStatus.FAILED,
                error_code="OPERATION_INTERRUPTED",
                error_message="処理を開始できませんでした。",
                retryable=True,
            )
            raise GenerationAlreadyRunningError("Repositoryの別の処理が実行中です。") from exc
        return job

    @staticmethod
    def _normalize_payload(payload: dict[str, object]) -> dict[str, object]:
        request = str(payload.get("request", "")).strip()
        if not 1 <= len(request) <= 4000:
            raise InvalidViewerOptionError("Requestは1〜4,000文字で指定してください。")
        additional = str(payload.get("additional_instruction") or "").strip() or None
        if additional and len(additional) > 4000:
            raise InvalidViewerOptionError("Additional Instructionは4,000文字以下です。")
        values = {
            "document_type": DOCUMENT_TYPES,
            "detail_level": DETAIL_LEVELS,
            "target_audience": TARGET_AUDIENCES,
            "theme_slug": THEMES,
            "density": DENSITIES,
        }
        normalized: dict[str, object] = {
            "request": request,
            "additional_instruction": additional,
        }
        for name, choices in values.items():
            value = payload.get(name)
            if value not in choices:
                raise InvalidViewerOptionError(f"{name}が不正です。")
            normalized[name] = value
        return normalized

    @staticmethod
    def _new_job(
        repository_id: UUID,
        idempotency_key: str,
        request_hash: str,
        payload: dict[str, object],
        *,
        commit_sha: str,
        operation: GenerationOperation,
        viewer_id: UUID | None = None,
        base_revision: int | None = None,
        retry_of: UUID | None = None,
    ) -> GenerationJobModel:
        now = datetime.now(UTC)
        return GenerationJobModel(
            id=uuid4(),
            repository_id=repository_id,
            viewer_id=viewer_id,
            retry_of_job_id=retry_of,
            operation=operation.value,
            status="queued",
            current_phase="queued",
            request=payload["request"],
            additional_instruction=payload["additional_instruction"],
            document_type=payload["document_type"],
            detail_level=payload["detail_level"],
            target_audience=payload["target_audience"],
            theme_slug=payload["theme_slug"],
            density=payload["density"],
            base_viewer_revision=base_revision,
            commit_sha=commit_sha,
            codex_thread_id=None,
            codex_turn_id=None,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            cancel_requested_at=None,
            started_at=None,
            completed_at=None,
            error_code=None,
            error_message=None,
            error_retryable=None,
            created_at=now,
            updated_at=now,
        )


def _request_hash(
    operation: str,
    repository_id: UUID,
    target_id: UUID | None,
    payload: dict[str, object],
) -> str:
    value = json.dumps(
        {
            "operation": operation,
            "repository_id": str(repository_id),
            "target_id": str(target_id) if target_id else None,
            "payload": payload,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode()).hexdigest()


def _viewer_payload(viewer: ViewerModel) -> dict[str, object]:
    return {
        "request": viewer.request,
        "additional_instruction": viewer.additional_instruction,
        "document_type": viewer.document_type,
        "detail_level": viewer.detail_level,
        "target_audience": viewer.target_audience,
        "theme_slug": viewer.theme_slug,
        "density": viewer.density,
    }
