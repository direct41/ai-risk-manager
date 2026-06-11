from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess  # nosec B404
from urllib import error, parse, request


class GitHubPRReviewError(RuntimeError):
    """Raised when a GitHub PR review checkout cannot be prepared."""


@dataclass(frozen=True)
class GitHubPRReference:
    repo_full_name: str
    pr_number: int
    clone_url: str


@dataclass(frozen=True)
class GitHubPRMetadata:
    base_ref: str
    base_sha: str
    head_sha: str


@dataclass(frozen=True)
class GitHubPRFilePatch:
    filename: str
    status: str
    additions: int
    deletions: int
    patch: str


@dataclass(frozen=True)
class GitHubPREvidence:
    title: str
    body: str
    state: str
    base_ref: str
    head_sha: str
    files: list[GitHubPRFilePatch]
    files_truncated: bool
    patches_truncated: bool


_SAFE_REF_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
_COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def parse_github_pr_url(raw_url: str) -> GitHubPRReference:
    parsed = parse.urlsplit(raw_url.strip())
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise GitHubPRReviewError("review-pr expects an https://github.com/<owner>/<repo>/pull/<number> URL.")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 4 or parts[2] != "pull" or not parts[3].isdigit():
        raise GitHubPRReviewError("review-pr expects a GitHub pull request URL.")

    owner, repo, _, number = parts
    repo_full_name = f"{owner}/{repo}"
    return GitHubPRReference(
        repo_full_name=repo_full_name,
        pr_number=int(number),
        clone_url=f"https://github.com/{repo_full_name}.git",
    )


def _api_url(api_base: str, path: str) -> str:
    base = api_base.rstrip("/")
    parsed = parse.urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise GitHubPRReviewError("GitHub API base must be an http(s) URL.")
    return f"{base}{path}"


def _safe_ref(ref: str) -> str:
    normalized = ref.strip()
    if not normalized or normalized.startswith("-") or "\x00" in normalized or not _SAFE_REF_RE.fullmatch(normalized):
        raise GitHubPRReviewError(f"Unsafe Git ref returned by GitHub API: {ref!r}")
    return normalized


def _safe_commit_sha(sha: str) -> str:
    normalized = sha.strip()
    if not _COMMIT_SHA_RE.fullmatch(normalized):
        raise GitHubPRReviewError(f"Invalid commit SHA returned by GitHub API: {sha!r}")
    return normalized.lower()


def fetch_github_pr_metadata(
    ref: GitHubPRReference,
    *,
    token: str = "",
    api_base: str = "https://api.github.com",
) -> GitHubPRMetadata:
    url = _api_url(api_base, f"/repos/{ref.repo_full_name}/pulls/{ref.pr_number}")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-risk-manager",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = request.Request(url, headers=headers, method="GET")
    try:
        with request.urlopen(req, timeout=20) as response:  # nosec B310
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        raise GitHubPRReviewError(f"GitHub API rejected PR lookup: HTTP {exc.code}.") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise GitHubPRReviewError(f"Unable to read GitHub PR metadata: {exc}") from exc

    base = payload.get("base")
    head = payload.get("head")
    if not isinstance(base, dict) or not isinstance(head, dict):
        raise GitHubPRReviewError("GitHub PR metadata response is missing base/head fields.")

    base_ref = base.get("ref")
    base_sha = base.get("sha")
    head_sha = head.get("sha")
    if not isinstance(base_ref, str) or not isinstance(base_sha, str) or not isinstance(head_sha, str):
        raise GitHubPRReviewError("GitHub PR metadata response is missing base ref, base SHA, or head SHA.")

    return GitHubPRMetadata(
        base_ref=_safe_ref(base_ref),
        base_sha=_safe_commit_sha(base_sha),
        head_sha=_safe_commit_sha(head_sha),
    )


def fetch_github_pr_evidence(
    ref: GitHubPRReference,
    *,
    token: str = "",
    api_base: str = "https://api.github.com",
    max_files: int = 100,
    max_patch_chars: int = 120_000,
) -> GitHubPREvidence:
    if max_files <= 0 or max_patch_chars <= 0:
        raise ValueError("GitHub PR evidence limits must be positive.")

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-risk-manager",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    pr_payload = _read_github_json(
        _api_url(api_base, f"/repos/{ref.repo_full_name}/pulls/{ref.pr_number}"),
        headers=headers,
    )
    if not isinstance(pr_payload, dict):
        raise GitHubPRReviewError("GitHub PR metadata response must be an object.")

    base = pr_payload.get("base")
    head = pr_payload.get("head")
    if not isinstance(base, dict) or not isinstance(head, dict):
        raise GitHubPRReviewError("GitHub PR metadata response is missing base/head fields.")
    base_ref = base.get("ref")
    head_sha = head.get("sha")
    if not isinstance(base_ref, str) or not isinstance(head_sha, str):
        raise GitHubPRReviewError("GitHub PR metadata response is missing base ref or head SHA.")

    raw_files: list[object] = []
    page = 1
    while len(raw_files) < max_files:
        page_payload = _read_github_json(
            _api_url(
                api_base,
                f"/repos/{ref.repo_full_name}/pulls/{ref.pr_number}/files?per_page=100&page={page}",
            ),
            headers=headers,
        )
        if not isinstance(page_payload, list):
            raise GitHubPRReviewError("GitHub PR files response must be a list.")
        raw_files.extend(page_payload[: max_files - len(raw_files)])
        if len(page_payload) < 100:
            break
        page += 1

    changed_files = pr_payload.get("changed_files")
    files_truncated = isinstance(changed_files, int) and changed_files > len(raw_files)
    patches_truncated = False
    remaining_patch_chars = max_patch_chars
    files: list[GitHubPRFilePatch] = []
    for raw_file in raw_files:
        if not isinstance(raw_file, dict):
            continue
        filename = raw_file.get("filename")
        if not isinstance(filename, str) or not filename:
            continue
        raw_patch = raw_file.get("patch")
        patch = raw_patch if isinstance(raw_patch, str) else ""
        if len(patch) > remaining_patch_chars:
            patch = patch[:remaining_patch_chars]
            patches_truncated = True
        remaining_patch_chars -= len(patch)
        if remaining_patch_chars <= 0:
            patches_truncated = True
        files.append(
            GitHubPRFilePatch(
                filename=filename,
                status=str(raw_file.get("status") or "unknown"),
                additions=_non_negative_int(raw_file.get("additions")),
                deletions=_non_negative_int(raw_file.get("deletions")),
                patch=patch,
            )
        )

    return GitHubPREvidence(
        title=str(pr_payload.get("title") or ""),
        body=str(pr_payload.get("body") or ""),
        state=str(pr_payload.get("state") or "unknown"),
        base_ref=_safe_ref(base_ref),
        head_sha=head_sha,
        files=files,
        files_truncated=files_truncated,
        patches_truncated=patches_truncated,
    )


def _read_github_json(url: str, *, headers: dict[str, str]) -> object:
    req = request.Request(url, headers=headers, method="GET")
    try:
        with request.urlopen(req, timeout=20) as response:  # nosec B310
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        raise GitHubPRReviewError(f"GitHub API rejected PR lookup: HTTP {exc.code}.") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise GitHubPRReviewError(f"Unable to read GitHub PR metadata: {exc}") from exc


def _non_negative_int(value: object) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _run_git(args: list[str], *, cwd: Path | None = None, timeout: int = 120) -> None:
    proc = subprocess.run(  # nosec B603
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise GitHubPRReviewError(f"git {' '.join(args)} failed: {detail}")


def prepare_github_pr_checkout(
    ref: GitHubPRReference,
    *,
    base_ref: str,
    base_sha: str | None = None,
    workspace: Path,
) -> Path:
    safe_base = _safe_ref(base_ref)
    safe_base_sha = _safe_commit_sha(base_sha) if base_sha is not None else None
    checkout_path = workspace / f"{ref.repo_full_name.replace('/', '-')}-pull-{ref.pr_number}"
    pr_branch = f"airisk-pr-{ref.pr_number}"

    _run_git(["clone", "--no-tags", "--depth=100", "--no-checkout", ref.clone_url, str(checkout_path)], timeout=180)
    fetch_refs = [
        f"refs/heads/{safe_base}:refs/remotes/origin/{safe_base}",
        f"refs/pull/{ref.pr_number}/head:refs/heads/{pr_branch}",
    ]
    if safe_base_sha is not None:
        fetch_refs.append(safe_base_sha)
    _run_git(
        [
            "fetch",
            "--depth=100",
            "origin",
            *fetch_refs,
        ],
        cwd=checkout_path,
        timeout=180,
    )
    _run_git(["checkout", "--detach", pr_branch], cwd=checkout_path)
    return checkout_path


def checkout_git_ref(repo_path: Path, ref: str) -> None:
    _run_git(["checkout", "--detach", _safe_ref(ref)], cwd=repo_path)


__all__ = [
    "GitHubPREvidence",
    "GitHubPRFilePatch",
    "GitHubPRMetadata",
    "GitHubPRReference",
    "GitHubPRReviewError",
    "checkout_git_ref",
    "fetch_github_pr_evidence",
    "fetch_github_pr_metadata",
    "parse_github_pr_url",
    "prepare_github_pr_checkout",
]
