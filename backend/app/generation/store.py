from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.generation.models import GenerationJobModel, GenerationStatus, ViewerModel
from backend.app.repositories.models import RepositoryModel, RepositoryStatus


class GenerationReservationError(RuntimeError):
    pass


class GenerationStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def get_viewer(self, viewer_id: UUID) -> ViewerModel | None:
        async with self.sessions() as session:
            return await session.get(ViewerModel, viewer_id)

    async def list_viewers(self, repository_id: UUID) -> list[ViewerModel]:
        async with self.sessions() as session:
            result = await session.scalars(
                select(ViewerModel)
                .where(ViewerModel.repository_id == repository_id)
                .order_by(ViewerModel.updated_at.desc())
            )
            return list(result)

    async def count_viewers(self, repository_id: UUID) -> int:
        async with self.sessions() as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(ViewerModel)
                    .where(ViewerModel.repository_id == repository_id)
                )
                or 0
            )

    async def get_job(self, job_id: UUID) -> GenerationJobModel | None:
        async with self.sessions() as session:
            return await session.get(GenerationJobModel, job_id)

    async def get_idempotent_job(self, repository_id: UUID, key: str) -> GenerationJobModel | None:
        async with self.sessions() as session:
            return await session.scalar(
                select(GenerationJobModel).where(
                    GenerationJobModel.repository_id == repository_id,
                    GenerationJobModel.idempotency_key == key,
                )
            )

    async def has_active_job(self, repository_id: UUID) -> bool:
        async with self.sessions() as session:
            return bool(
                await session.scalar(
                    select(
                        exists().where(
                            GenerationJobModel.repository_id == repository_id,
                            GenerationJobModel.status.in_(["queued", "running"]),
                        )
                    )
                )
            )

    async def has_active_viewer_job(self, viewer_id: UUID) -> bool:
        async with self.sessions() as session:
            return bool(
                await session.scalar(
                    select(
                        exists().where(
                            GenerationJobModel.viewer_id == viewer_id,
                            GenerationJobModel.status.in_(["queued", "running"]),
                        )
                    )
                )
            )

    async def is_queued(self, job_id: UUID) -> bool:
        async with self.sessions() as session:
            return (
                await session.scalar(
                    select(GenerationJobModel.id).where(
                        GenerationJobModel.id == job_id,
                        GenerationJobModel.status == GenerationStatus.QUEUED.value,
                        GenerationJobModel.cancel_requested_at.is_(None),
                    )
                )
            ) is not None

    async def create_job(self, job: GenerationJobModel) -> GenerationJobModel:
        async with self.sessions() as session:
            repository = await session.scalar(
                select(RepositoryModel)
                .where(RepositoryModel.id == job.repository_id)
                .with_for_update()
            )
            if repository is None or repository.status != RepositoryStatus.READY.value:
                raise GenerationReservationError("Repository is not ready")
            active_job = await session.scalar(
                select(GenerationJobModel.id)
                .where(
                    GenerationJobModel.repository_id == job.repository_id,
                    GenerationJobModel.status.in_(["queued", "running"]),
                )
                .limit(1)
            )
            if active_job is not None:
                raise GenerationReservationError("Generation is already active")
            session.add(job)
            await session.commit()
            return job

    async def set_running(self, job_id: UUID) -> bool:
        now = datetime.now(UTC)
        async with self.sessions() as session:
            result = await session.execute(
                update(GenerationJobModel)
                .where(
                    GenerationJobModel.id == job_id,
                    GenerationJobModel.status == GenerationStatus.QUEUED.value,
                    GenerationJobModel.cancel_requested_at.is_(None),
                )
                .values(
                    status=GenerationStatus.RUNNING.value,
                    current_phase="preparing_repository",
                    started_at=now,
                    updated_at=now,
                )
            )
            await session.commit()
            return result.rowcount == 1

    async def set_phase(self, job_id: UUID, phase: str, **values: object) -> bool:
        values.update(current_phase=phase, updated_at=datetime.now(UTC))
        async with self.sessions() as session:
            result = await session.execute(
                update(GenerationJobModel)
                .where(
                    GenerationJobModel.id == job_id,
                    GenerationJobModel.status == GenerationStatus.RUNNING.value,
                )
                .values(**values)
            )
            await session.commit()
            return result.rowcount == 1

    async def request_cancel(self, job_id: UUID) -> GenerationJobModel | None:
        now = datetime.now(UTC)
        async with self.sessions() as session:
            job = await session.get(GenerationJobModel, job_id, with_for_update=True)
            if job is None:
                return None
            if job.status == GenerationStatus.QUEUED.value:
                job.cancel_requested_at = now
                job.status = GenerationStatus.CANCELLED.value
                job.completed_at = now
            elif job.status == GenerationStatus.RUNNING.value and job.cancel_requested_at is None:
                job.cancel_requested_at = now
            job.updated_at = now
            await session.commit()
            return job

    async def is_cancel_requested(self, job_id: UUID) -> bool:
        async with self.sessions() as session:
            value = await session.scalar(
                select(GenerationJobModel.cancel_requested_at).where(
                    GenerationJobModel.id == job_id
                )
            )
            return value is not None

    async def mark_terminal(
        self,
        job_id: UUID,
        status: GenerationStatus,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        retryable: bool | None = None,
    ) -> bool:
        now = datetime.now(UTC)
        async with self.sessions() as session:
            result = await session.execute(
                update(GenerationJobModel)
                .where(
                    GenerationJobModel.id == job_id,
                    GenerationJobModel.status.in_(["queued", "running"]),
                )
                .values(
                    status=status.value,
                    completed_at=now,
                    updated_at=now,
                    error_code=error_code,
                    error_message=error_message[:500] if error_message else None,
                    error_retryable=retryable,
                )
            )
            await session.commit()
            return result.rowcount == 1

    async def save_viewer(
        self,
        job_id: UUID,
        viewer: ViewerModel,
        base_revision: int | None,
    ) -> bool:
        now = datetime.now(UTC)
        async with self.sessions() as session:
            job = await session.get(GenerationJobModel, job_id, with_for_update=True)
            if (
                job is None
                or job.status != GenerationStatus.RUNNING.value
                or job.cancel_requested_at is not None
            ):
                return False
            if base_revision is None:
                session.add(viewer)
            else:
                result = await session.execute(
                    update(ViewerModel)
                    .where(
                        ViewerModel.id == viewer.id,
                        ViewerModel.content_revision == base_revision,
                    )
                    .values(
                        title=viewer.title,
                        summary=viewer.summary,
                        content_json=viewer.content_json,
                        sanitized_html=viewer.sanitized_html,
                        commit_sha=viewer.commit_sha,
                        renderer_version=viewer.renderer_version,
                        content_revision=base_revision + 1,
                        updated_at=now,
                    )
                )
                if result.rowcount != 1:
                    await session.rollback()
                    return False
            job.viewer_id = viewer.id
            job.status = GenerationStatus.COMPLETED.value
            job.current_phase = "completed"
            job.completed_at = now
            job.updated_at = now
            await session.commit()
            return True

    async def update_appearance(
        self, viewer_id: UUID, theme_slug: str | None, density: str | None
    ) -> ViewerModel | None:
        values: dict[str, object] = {"updated_at": datetime.now(UTC)}
        if theme_slug is not None:
            values["theme_slug"] = theme_slug
        if density is not None:
            values["density"] = density
        async with self.sessions() as session:
            result = await session.execute(
                update(ViewerModel).where(ViewerModel.id == viewer_id).values(**values)
            )
            await session.commit()
            return await session.get(ViewerModel, viewer_id) if result.rowcount else None

    async def delete_viewer(self, viewer_id: UUID) -> bool:
        async with self.sessions() as session:
            result = await session.execute(delete(ViewerModel).where(ViewerModel.id == viewer_id))
            await session.commit()
            return result.rowcount == 1

    async def recover_interrupted(self) -> list[UUID]:
        now = datetime.now(UTC)
        async with self.sessions() as session:
            ids = list(
                await session.scalars(
                    select(GenerationJobModel.id).where(
                        GenerationJobModel.status.in_(["queued", "running"])
                    )
                )
            )
            await session.execute(
                update(GenerationJobModel)
                .where(GenerationJobModel.id.in_(ids))
                .values(
                    status="failed",
                    error_code="OPERATION_INTERRUPTED",
                    error_message="処理が中断されました。再試行してください。",
                    error_retryable=True,
                    completed_at=now,
                    updated_at=now,
                )
            )
            await session.commit()
            return ids

    async def cleanup_terminal(self, retention_days: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        async with self.sessions() as session:
            result = await session.execute(
                delete(GenerationJobModel).where(
                    GenerationJobModel.status.in_(["completed", "failed", "cancelled"]),
                    GenerationJobModel.updated_at < cutoff,
                )
            )
            await session.commit()
            return result.rowcount
