from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urlparse

import nh3

ALLOWED_TAGS = {
    "article",
    "section",
    "div",
    "nav",
    "aside",
    "h2",
    "h3",
    "h4",
    "p",
    "ul",
    "ol",
    "li",
    "dl",
    "dt",
    "dd",
    "table",
    "caption",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "pre",
    "code",
    "strong",
    "em",
    "span",
    "button",
    "a",
}
ALLOWED_ATTRIBUTES = {
    "*": {
        "class",
        "id",
        "role",
        "aria-label",
        "aria-live",
        "aria-busy",
        "data-block-type",
        "data-source-reference-id",
    },
    "button": {"type"},
    "th": {"scope"},
    "a": {"href", "target", "rel"},
}


class HtmlSanitizeError(RuntimeError):
    pass


def sanitize_viewer_html(html: str, repository_github_url: str) -> str:
    cleaned = nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes={"https"},
        link_rel=None,
        strip_comments=True,
    )
    validator = _UrlValidator(repository_github_url)
    validator.feed(cleaned)
    if validator.error:
        raise HtmlSanitizeError(validator.error)
    return cleaned


class _UrlValidator(HTMLParser):
    def __init__(self, repository_github_url: str) -> None:
        super().__init__()
        parsed = urlparse(repository_github_url)
        self.allowed_prefix = f"https://{parsed.netloc}{parsed.path.rstrip('/')}/"
        self.error: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag != "a" or "href" not in values:
            return
        href = values["href"] or ""
        if href.startswith("#"):
            return
        if not href.startswith(self.allowed_prefix):
            self.error = "Viewer HTML contains a URL outside the repository"
        if values.get("target") != "_blank" or values.get("rel") != "noopener noreferrer":
            self.error = "External links require a safe target and rel"
