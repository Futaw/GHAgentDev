import pytest

from backend.app.repositories.url import InvalidGitHubUrlError, normalize_github_url


@pytest.mark.parametrize(
    ("raw", "owner", "name", "canonical"),
    [
        (
            "https://github.com/Futaw/GHAgentDev",
            "Futaw",
            "GHAgentDev",
            "https://github.com/futaw/ghagentdev",
        ),
        (
            " https://github.com/Futaw/GHAgentDev.git/ ",
            "Futaw",
            "GHAgentDev",
            "https://github.com/futaw/ghagentdev",
        ),
        (
            "https://github.com/a/repo.name_1",
            "a",
            "repo.name_1",
            "https://github.com/a/repo.name_1",
        ),
    ],
)
def test_normalize_github_url(raw: str, owner: str, name: str, canonical: str) -> None:
    result = normalize_github_url(raw)
    assert (result.owner, result.name, result.canonical_url) == (owner, name, canonical)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "http://github.com/owner/repo",
        "https://www.github.com/owner/repo",
        "https://user@github.com/owner/repo",
        "https://github.com:443/owner/repo",
        "https://github.com/owner/repo/tree/main",
        "https://github.com/owner/repo?tab=readme",
        "https://github.com/owner/repo#readme",
        "https://github.com/owner/%72epo",
        "git@github.com:owner/repo.git",
        "file:///tmp/repo",
        "https://github.com/-/..",
    ],
)
def test_reject_invalid_github_url(raw: str) -> None:
    with pytest.raises(InvalidGitHubUrlError):
        normalize_github_url(raw)
