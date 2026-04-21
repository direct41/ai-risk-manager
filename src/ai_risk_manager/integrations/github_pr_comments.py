from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from ai_risk_manager import __version__

PR_SUMMARY_MARKER = "<!-- ai-risk-manager -->"


class GitHubCommentError(RuntimeError):
    """Raised when GitHub PR comment publication fails."""


def load_pr_comment_body(path: Path) -> str:
    try:
        body = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise GitHubCommentError(f"Unable to read PR comment body from {path}: {exc}") from exc
    if not body:
        raise GitHubCommentError(f"PR comment body file is empty: {path}")
    return body


def _api_url(api_base: str, path: str) -> str:
    base = api_base.rstrip("/")
    parsed = parse.urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise GitHubCommentError("GitHub API base must be an http(s) URL.")
    return f"{base}{path}"


def _comment_id(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError as exc:
            raise GitHubCommentError(f"GitHub API returned a non-numeric comment id: {value!r}") from exc
    raise GitHubCommentError("GitHub API returned a comment payload without a valid id.")


def _github_json_request(
    *,
    api_base: str,
    path: str,
    token: str,
    method: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        _api_url(api_base, path),
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"ai-risk-manager/{__version__}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        # URL scheme and host are validated by _api_url before Request construction.
        with request.urlopen(req, timeout=20) as response:  # nosec B310
            raw = response.read()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise GitHubCommentError(f"GitHub API {method} {path} failed with {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise GitHubCommentError(f"GitHub API {method} {path} failed: {exc.reason}") from exc

    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise GitHubCommentError(f"GitHub API returned invalid JSON for {method} {path}") from exc


def upsert_pr_comment(
    *,
    repo_full_name: str,
    pr_number: int,
    body: str,
    token: str,
    api_base: str = "https://api.github.com",
) -> tuple[str, int]:
    if not token.strip():
        raise GitHubCommentError("GitHub token is empty.")
    if PR_SUMMARY_MARKER not in body:
        body = f"{PR_SUMMARY_MARKER}\n{body.strip()}"

    safe_repo = parse.quote(repo_full_name, safe="/")
    comments = _github_json_request(
        api_base=api_base,
        path=f"/repos/{safe_repo}/issues/{pr_number}/comments?per_page=100",
        token=token,
        method="GET",
    )
    if not isinstance(comments, list):
        raise GitHubCommentError("GitHub API returned an unexpected comments payload.")

    existing = next(
        (
            row
            for row in comments
            if isinstance(row, dict) and PR_SUMMARY_MARKER in str(row.get("body", ""))
        ),
        None,
    )

    if existing is not None:
        comment_id = _comment_id(existing.get("id"))
        _github_json_request(
            api_base=api_base,
            path=f"/repos/{safe_repo}/issues/comments/{comment_id}",
            token=token,
            method="PATCH",
            payload={"body": body},
        )
        return "updated", comment_id

    created = _github_json_request(
        api_base=api_base,
        path=f"/repos/{safe_repo}/issues/{pr_number}/comments",
        token=token,
        method="POST",
        payload={"body": body},
    )
    if not isinstance(created, dict) or "id" not in created:
        raise GitHubCommentError("GitHub API returned an unexpected create-comment payload.")
    return "created", _comment_id(created["id"])


__all__ = ["GitHubCommentError", "PR_SUMMARY_MARKER", "load_pr_comment_body", "upsert_pr_comment"]
