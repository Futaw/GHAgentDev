from __future__ import annotations

from collections.abc import Collection
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.repositories.models import RepositoryModel, RepositoryStatus


class DuplicateRepositoryError(RuntimeError):
    def __init__(self, repository_id: UUID | None = None) -> None:
        super().__init__("Repository is already registered")
        self.repository_id = repository_id


class RepositoryStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def create(self, repository: RepositoryModel) -> RepositoryModel:
        async with self.sessions() as session:
            session.add(repository)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                existing = await session.scalar(
                    select(RepositoryModel).where(
                        RepositoryModel.canonical_github_url == repository.canonical_github_url
                    )
                )
                raise DuplicateRepositoryError(existing.id if existing else None) from exc
            return repository

    async def list(self) -> list[RepositoryModel]:
        async with self.sessions() as session:
            result = await session.scalars(
                select(RepositoryModel).order_by(RepositoryModel.updated_at.desc())
            )
            return list(result)

    async def get(self, repository_id: UUID) -> RepositoryModel | None:
        async with self.sessions() as session:
            return await session.get(RepositoryModel, repository_id)

    async def get_by_url(self, canonical_url: str) -> RepositoryModel | None:
        async with self.sessions() as session:
            return await session.scalar(
                select(RepositoryModel).where(RepositoryModel.canonical_github_url == canonical_url)
            )

    async def begin_operation(
        self,
        repository_id: UUID,
        expected: Collection[RepositoryStatus],
        new_status: RepositoryStatus,
    ) -> RepositoryModel | None:
        now = datetime.now(UTC)
        async with self.sessions() as session:
            result = await session.execute(
                update(RepositoryModel)
                .where(
                    RepositoryModel.id == repository_id,
                    RepositoryModel.status.in_([item.value for item in expected]),
                )
                .values(
                    status=new_status.value,
                    last_error_code=None,
                    last_error_message=None,
                    updated_at=now,
                )
            )
            await session.commit()
            if result.rowcount != 1:
                return None
            return await session.get(RepositoryModel, repository_id)

    async def mark_ready(
        self,
        repository_id: UUID,
        default_branch: str,
        commit_sha: str,
    ) -> None:
        now = datetime.now(UTC)
        async with self.sessions() as session:
            await session.execute(
                update(RepositoryModel)
                .where(
                    RepositoryModel.id == repository_id,
                    RepositoryModel.status.in_(
                        [
                            RepositoryStatus.CLONING.value,
                            RepositoryStatus.SYNCING.value,
                        ]
                    ),
                )
                .values(
                    status=RepositoryStatus.READY.value,
                    default_branch=default_branch,
                    latest_commit_sha=commit_sha,
                    last_synced_at=now,
                    last_error_code=None,
                    last_error_message=None,
                    updated_at=now,
                )
            )
            await session.commit()

    async def mark_failed(self, repository_id: UUID, code: str, message: str) -> None:
        async with self.sessions() as session:
            await session.execute(
                update(RepositoryModel)
                .where(RepositoryModel.id == repository_id)
                .values(
                    status=RepositoryStatus.FAILED.value,
                    last_error_code=code,
                    last_error_message=message[:500],
                    updated_at=datetime.now(UTC),
                )
            )
            await session.commit()

    async def recover_interrupted(self) -> int:
        async with self.sessions() as session:
            result = await session.execute(
                update(RepositoryModel)
                .where(
                    RepositoryModel.status.in_(
                        [
                            RepositoryStatus.PENDING.value,
                            RepositoryStatus.CLONING.value,
                            RepositoryStatus.SYNCING.value,
                        ]
                    )
                )
                .values(
                    status=RepositoryStatus.FAILED.value,
                    last_error_code="OPERATION_INTERRUPTED",
                    last_error_message="処理が中断されました。再試行してください。",
                    updated_at=datetime.now(UTC),
                )
            )
            await session.commit()
            return result.rowcount
