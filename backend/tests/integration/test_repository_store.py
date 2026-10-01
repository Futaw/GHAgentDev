from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.repositories.models import Base, RepositoryModel, RepositoryStatus
from backend.app.repositories.store import DuplicateRepositoryError, RepositoryStore


def repository_model(url: str = "https://github.com/example/repo") -> RepositoryModel:
    repository_id = uuid4()
    now = datetime.now(UTC)
    return RepositoryModel(
        id=repository_id,
        owner="Example",
        name="Repo",
        canonical_github_url=url,
        workspace_key=str(repository_id),
        status=RepositoryStatus.PENDING.value,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_store_crud_duplicate_and_interrupted_recovery(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'repositories.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    store = RepositoryStore(async_sessionmaker(engine, expire_on_commit=False))
    first = repository_model()
    await store.create(first)

    duplicate = repository_model()
    duplicate.canonical_github_url = first.canonical_github_url
    with pytest.raises(DuplicateRepositoryError) as error:
        await store.create(duplicate)
    assert error.value.repository_id == first.id

    started = await store.begin_operation(
        first.id, {RepositoryStatus.PENDING}, RepositoryStatus.CLONING
    )
    assert started is not None and started.status == RepositoryStatus.CLONING.value
    assert await store.recover_interrupted() == 1
    recovered = await store.get(first.id)
    assert recovered is not None
    assert recovered.status == RepositoryStatus.FAILED.value
    assert recovered.last_error_code == "OPERATION_INTERRUPTED"

    successful = repository_model("https://github.com/example/another")
    await store.create(successful)
    await store.begin_operation(successful.id, {RepositoryStatus.PENDING}, RepositoryStatus.CLONING)
    await store.mark_ready(successful.id, "main", "a" * 40)
    before_failure = await store.get(successful.id)
    await store.begin_operation(successful.id, {RepositoryStatus.READY}, RepositoryStatus.SYNCING)
    await store.mark_failed(successful.id, "SYNC_FAILED", "同期できませんでした。")
    after_failure = await store.get(successful.id)
    assert before_failure is not None and after_failure is not None
    assert after_failure.default_branch == before_failure.default_branch == "main"
    assert after_failure.latest_commit_sha == before_failure.latest_commit_sha == "a" * 40
    assert after_failure.last_synced_at == before_failure.last_synced_at
    await engine.dispose()
