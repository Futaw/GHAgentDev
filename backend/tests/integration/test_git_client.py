import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.repositories.git import GitClient, GitOperationError
from backend.app.repositories.workspace import WorkspaceResolver


def run_git(*arguments: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@pytest.mark.asyncio
async def test_git_client_clones_and_syncs_local_bare_repository(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    source = tmp_path / "source.git"
    seed.mkdir()
    run_git("init", "-b", "main", cwd=seed)
    run_git("config", "user.name", "RepoSpec Test", cwd=seed)
    run_git("config", "user.email", "test@example.invalid", cwd=seed)
    (seed / "README.md").write_text("first\n")
    run_git("add", "README.md", cwd=seed)
    run_git("commit", "-m", "first", cwd=seed)
    run_git("clone", "--bare", str(seed), str(source))

    workspace = WorkspaceResolver(tmp_path / "managed")
    workspace.prepare()
    client = GitClient(
        "git", workspace, 10, 10, 10_000_000, 100, allow_local_sources_for_tests=True
    )
    repository_id = uuid4()
    destination = workspace.repository_path(str(repository_id))
    metadata = await client.clone(str(source), workspace.staging_path(uuid4()), destination)
    assert metadata.default_branch == "main"
    assert metadata.commit_sha == run_git("rev-parse", "HEAD", cwd=seed)

    run_git("remote", "add", "origin", str(source), cwd=seed)
    (seed / "README.md").write_text("second\n")
    run_git("commit", "-am", "second", cwd=seed)
    run_git("push", "origin", "main", cwd=seed)

    updated = await client.sync(destination, str(source))
    assert updated.commit_sha == run_git("rev-parse", "HEAD", cwd=seed)
    assert (destination / "README.md").read_text() == "second\n"

    limited = GitClient("git", workspace, 10, 10, 1, 100, allow_local_sources_for_tests=True)
    limited_staging = workspace.staging_path(uuid4())
    with pytest.raises(GitOperationError, match="容量") as error:
        await limited.clone(str(source), limited_staging, workspace.repository_path(str(uuid4())))
    assert error.value.code == "REPOSITORY_TOO_LARGE"
    assert not limited_staging.exists()


@pytest.mark.asyncio
async def test_git_client_converts_timeout_without_exposing_process_output(tmp_path: Path) -> None:
    executable = tmp_path / "slow-git"
    executable.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(5)\n")
    executable.chmod(0o700)
    workspace = WorkspaceResolver(tmp_path / "managed")
    workspace.prepare()
    client = GitClient(str(executable), workspace, 0.01, 0.01, 100, 10)

    with pytest.raises(GitOperationError, match="タイムアウト") as error:
        await client._run([], 0.01)
    assert error.value.code == "SYNC_FAILED"
    assert str(tmp_path) not in str(error.value)
