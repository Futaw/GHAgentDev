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
