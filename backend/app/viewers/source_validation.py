from __future__ import annotations

import asyncio

from backend.app.viewers.document import SourceReference


class SourceReferenceError(RuntimeError):
    pass


class SourceReferenceValidator:
    def __init__(self, git_executable: str = "git", max_blob_bytes: int = 2_097_152) -> None:
        self.git_executable = git_executable
        self.max_blob_bytes = max_blob_bytes

    async def validate(
        self,
        repository: str,
        commit_sha: str,
        references: list[SourceReference],
    ) -> None:
        tree = await self._tree(repository, commit_sha)
        for reference in references:
            self._validate_path(reference.path)
            entry = tree.get(reference.path)
            if not entry or entry[0] != "100644" or entry[1] != "blob":
                raise SourceReferenceError("Source reference is not a regular tracked file")
            blob = await self._run(repository, ["cat-file", "blob", entry[2]])
            if len(blob) > self.max_blob_bytes or b"\0" in blob:
                raise SourceReferenceError("Source reference is binary or too large")
            try:
                text = blob.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise SourceReferenceError("Source reference is not UTF-8 text") from exc
            line_count = len(text.splitlines())
            if reference.end_line > line_count:
                raise SourceReferenceError("Source reference line range is outside the blob")

    @staticmethod
    def _validate_path(value: str) -> None:
        if "\0" in value or "\\" in value or value.startswith("/"):
            raise SourceReferenceError("Invalid source path")
        if not value or any(part in {"", ".", ".."} for part in value.split("/")):
            raise SourceReferenceError("Invalid source path")

    async def _tree(self, repository: str, commit_sha: str) -> dict[str, tuple[str, str, str]]:
        raw = await self._run(repository, ["ls-tree", "-r", "-z", commit_sha])
        result: dict[str, tuple[str, str, str]] = {}
        for item in raw.split(b"\0"):
            if not item:
                continue
            metadata, raw_path = item.split(b"\t", 1)
            mode, kind, object_id = metadata.decode("ascii").split(" ")
            result[raw_path.decode("utf-8")] = (mode, kind, object_id)
        return result

    async def _run(self, repository: str, arguments: list[str]) -> bytes:
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
            raise SourceReferenceError("Git object could not be validated")
        return stdout
