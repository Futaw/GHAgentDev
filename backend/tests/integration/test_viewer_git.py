from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.viewers.document import SourceReference
from backend.app.viewers.git_refs import ViewerGitRefs, generation_ref, viewer_revision_ref
from backend.app.viewers.source_validation import SourceReferenceError, SourceReferenceValidator


async def git(path: Path, *arguments: str) -> str:
    process = await asyncio.create_subprocess_exec(
        "git", "-C", str(path), *arguments, stdout=asyncio.subprocess.PIPE
    )
    stdout, _ = await process.communicate()
    assert process.returncode == 0
    return stdout.decode().strip()


@pytest.mark.asyncio
async def test_source_validation_and_revision_refs(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    await git(repository, "init")
    await git(repository, "config", "user.email", "test@example.com")
    await git(repository, "config", "user.name", "Test")
    (repository / "main.py").write_text("line one\nline two\n")
    await git(repository, "add", "main.py")
    await git(repository, "commit", "-m", "fixture")
    commit = await git(repository, "rev-parse", "HEAD")

    validator = SourceReferenceValidator(max_blob_bytes=1024)
    valid = SourceReference(
        id="source", path="main.py", start_line=1, end_line=2, description="fixture"
    )
    await validator.validate(str(repository), commit, [valid])
    with pytest.raises(SourceReferenceError, match="line range"):
        await validator.validate(
            str(repository),
            commit,
            [valid.model_copy(update={"end_line": 3})],
        )
    with pytest.raises(SourceReferenceError, match="path"):
        await validator.validate(
            str(repository),
            commit,
            [valid.model_copy(update={"path": "../main.py"})],
        )

    job_id, viewer_id = uuid4(), uuid4()
    refs = ViewerGitRefs()
    temporary = generation_ref(job_id)
    revision = viewer_revision_ref(viewer_id, 1)
    await refs.create(str(repository), temporary, commit)
    await refs.create(str(repository), revision, commit)
    assert await refs.resolve(str(repository), temporary) == commit
    assert await refs.resolve(str(repository), revision) == commit
    assert await refs.reconcile(str(repository), {revision}) == [temporary]
    assert await refs.resolve(str(repository), temporary) is None
    await refs.delete_viewer(str(repository), viewer_id)
    assert await refs.resolve(str(repository), temporary) is None
    assert await refs.resolve(str(repository), revision) is None


@pytest.mark.asyncio
async def test_source_validation_rejects_symlink_binary_and_submodule(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    await git(repository, "init")
    await git(repository, "config", "user.email", "test@example.com")
    await git(repository, "config", "user.name", "Test")
    (repository / "target.txt").write_text("target\n")
    (repository / "binary.bin").write_bytes(b"a\0b")
    (repository / "link").symlink_to("target.txt")
    await git(repository, "add", ".")
    await git(repository, "commit", "-m", "unsafe fixtures")
    commit = await git(repository, "rev-parse", "HEAD")
    validator = SourceReferenceValidator()
    for path in ("link", "binary.bin"):
        reference = SourceReference(
            id="source", path=path, start_line=1, end_line=1, description="unsafe"
        )
        with pytest.raises(SourceReferenceError):
            await validator.validate(str(repository), commit, [reference])
