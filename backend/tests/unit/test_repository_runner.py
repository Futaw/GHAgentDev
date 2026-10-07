import asyncio
from uuid import uuid4

import pytest

from backend.app.repositories import RepositoryBusyError, RepositoryOperationRunner


@pytest.mark.asyncio
async def test_runner_rejects_two_operations_for_same_repository() -> None:
    runner = RepositoryOperationRunner()
    repository_id = uuid4()
    started = asyncio.Event()
    release = asyncio.Event()

    async def operation() -> None:
        started.set()
        await release.wait()

    runner.schedule(repository_id, operation)
    await started.wait()
    with pytest.raises(RepositoryBusyError):
        runner.schedule(repository_id, operation)
    release.set()
    await runner.shutdown()


@pytest.mark.asyncio
async def test_runner_exclusive_lock_rejects_background_and_second_delete() -> None:
    runner = RepositoryOperationRunner()
    repository_id = uuid4()

    async def operation() -> None:
        await asyncio.sleep(0)

    async with runner.exclusive(repository_id):
        with pytest.raises(RepositoryBusyError):
            runner.schedule(repository_id, operation)
        with pytest.raises(RepositoryBusyError):
            async with runner.exclusive(repository_id):
                pass
    await runner.shutdown()
