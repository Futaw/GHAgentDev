from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit


class InvalidGitHubUrlError(ValueError):
    pass


@dataclass(frozen=True)
class GitHubRepositoryUrl:
    owner: str
    name: str
    canonical_url: str


OWNER_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,39}$")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


def normalize_github_url(raw_url: str) -> GitHubRepositoryUrl:
    value = raw_url.strip()
    if not 1 <= len(value) <= 2048 or "%" in value:
        raise InvalidGitHubUrlError("GitHub URLの形式を確認してください。")
    if value.endswith("/"):
        value = value[:-1]
    try:
        parsed = urlsplit(value)
        explicit_port = parsed.port
    except ValueError as exc:
        raise InvalidGitHubUrlError("GitHub URLの形式を確認してください。") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or explicit_port is not None
        or parsed.query
        or parsed.fragment
    ):
        raise InvalidGitHubUrlError("https://github.com/owner/repository 形式で入力してください。")
    segments = parsed.path.split("/")
    if len(segments) != 3 or segments[0] or not segments[1] or not segments[2]:
        raise InvalidGitHubUrlError("RepositoryまでのGitHub URLを入力してください。")
    owner, name = segments[1], segments[2]
    if name.endswith(".git"):
        name = name[:-4]
    if (
        owner in {".", ".."}
        or name in {"", ".", ".."}
        or not OWNER_PATTERN.fullmatch(owner)
        or not REPOSITORY_PATTERN.fullmatch(name)
    ):
        raise InvalidGitHubUrlError("ownerまたはRepository名の形式を確認してください。")
    return GitHubRepositoryUrl(
        owner=owner,
        name=name,
        canonical_url=f"https://github.com/{owner.lower()}/{name.lower()}",
    )
