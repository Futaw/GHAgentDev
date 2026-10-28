from __future__ import annotations

import asyncio
from uuid import UUID


class GitRefError(RuntimeError):
    pass


def generation_ref(job_id: UUID) -> str:
    return f"refs/repospec/generation/{job_id}"


def viewer_revision_ref(viewer_id: UUID, revision: int) -> str:
    if revision < 1:
        raise ValueError("revision must be positive")
    return f"refs/repospec/viewers/{viewer_id}/revisions/{revision}"


class ViewerGitRefs:
    def __init__(self, git_executable: str = "git") -> None:
        self.git_executable = git_executable

    async def create(self, repository: str, ref: str, commit_sha: str) -> None:
        await self._run(repository, "update-ref", ref, commit_sha, "0" * 40)

    async def delete(self, repository: str, ref: str, *, missing_ok: bool = True) -> None:
        try:
            await self._run(repository, "update-ref", "-d", ref)
        except GitRefError:
            if not missing_ok:
                raise

    async def delete_viewer(self, repository: str, viewer_id: UUID) -> None:
        prefix = f"refs/repospec/viewers/{viewer_id}/revisions/"
        raw = await self._run(repository, "for-each-ref", "--format=%(refname)", prefix)
        for ref in raw.decode().splitlines():
            await self.delete(repository, ref)

    async def reconcile(self, repository: str, expected: set[str]) -> list[str]:
        """Delete stale RepoSpec refs and return their names for safe diagnostics."""
        raw = await self._run(repository, "for-each-ref", "--format=%(refname)", "refs/repospec/")
        stale = [ref for ref in raw.decode().splitlines() if ref not in expected]
        for ref in stale:
            await self.delete(repository, ref, missing_ok=False)
        return stale

    async def resolve(self, repository: str, ref: str) -> str | None:
        try:
            return (await self._run(repository, "rev-parse", "--verify", ref)).decode().strip()
        except GitRefError:
            return None

    async def _run(self, repository: str, *arguments: str) -> bytes:
        process = await asyncio.create_subprocess_exec(
            self.git_executable,
            "-C",
            repository,
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await process.communicate()
        if process.returncode != 0:
            raise GitRefError("Git ref operation failed")
        return stdout
