from __future__ import annotations

import json
from pathlib import Path
from urllib import request

from ai_risk_manager.cli import main
from ai_risk_manager.integrations.github_pr_comments import (
    GitHubCommentError,
    PR_SUMMARY_MARKER,
    load_pr_comment_body,
    upsert_pr_comment,
)


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_load_pr_comment_body_requires_non_empty_file(tmp_path: Path, write_file) -> None:
    path = tmp_path / "pr_summary.md"
    write_file(path, "")

    try:
        load_pr_comment_body(path)
    except GitHubCommentError as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("Expected GitHubCommentError")


def test_upsert_pr_comment_updates_existing_comment(monkeypatch) -> None:
    calls: list[tuple[str, str, str | None]] = []

    def _fake_urlopen(req: request.Request, timeout: int = 20):  # type: ignore[override]
        body = req.data.decode("utf-8") if req.data else None
        calls.append((req.method, req.full_url, body))
        if req.method == "GET":
            return _FakeResponse([{"id": 42, "body": f"{PR_SUMMARY_MARKER}\nold"}])
        if req.method == "PATCH":
            return _FakeResponse({"id": 42, "body": json.loads(body or "{}")["body"]})
        raise AssertionError(f"Unexpected method: {req.method}")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)

    action, comment_id = upsert_pr_comment(
        repo_full_name="owner/repo",
        pr_number=5,
        body="## AI Risk Manager\nupdated",
        token="secret",
    )

    assert action == "updated"
    assert comment_id == 42
    assert calls[0][0] == "GET"
    assert calls[1][0] == "PATCH"
    assert PR_SUMMARY_MARKER in (calls[1][2] or "")


def test_upsert_pr_comment_creates_when_marker_not_found(monkeypatch) -> None:
    calls: list[tuple[str, str, str | None]] = []

    def _fake_urlopen(req: request.Request, timeout: int = 20):  # type: ignore[override]
        body = req.data.decode("utf-8") if req.data else None
        calls.append((req.method, req.full_url, body))
        if req.method == "GET":
            return _FakeResponse([])
        if req.method == "POST":
            return _FakeResponse({"id": 99, "body": json.loads(body or "{}")["body"]})
        raise AssertionError(f"Unexpected method: {req.method}")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)

    action, comment_id = upsert_pr_comment(
        repo_full_name="owner/repo",
        pr_number=7,
        body=f"{PR_SUMMARY_MARKER}\n## AI Risk Manager\ncreated",
        token="secret",
    )

    assert action == "created"
    assert comment_id == 99
    assert calls[0][0] == "GET"
    assert calls[1][0] == "POST"


def test_cli_publish_pr_comment_supports_dry_run(tmp_path: Path, write_file, capsys) -> None:
    summary = tmp_path / "pr_summary.md"
    write_file(summary, "## AI Risk Manager\nbody")

    code = main(
        [
            "publish-pr-comment",
            "--repo",
            "owner/repo",
            "--pr-number",
            "12",
            "--summary-file",
            str(summary),
            "--dry-run",
        ]
    )

    assert code == 0
    output = capsys.readouterr().out
    assert "## AI Risk Manager" in output


def test_cli_publish_pr_comment_invokes_upsert(tmp_path: Path, write_file, monkeypatch, capsys) -> None:
    summary = tmp_path / "pr_summary.md"
    write_file(summary, "## AI Risk Manager\nbody")
    monkeypatch.setenv("GITHUB_TOKEN", "secret")

    captured: dict[str, object] = {}

    def _fake_upsert(*, repo_full_name: str, pr_number: int, body: str, token: str, api_base: str):
        captured.update(
            {
                "repo_full_name": repo_full_name,
                "pr_number": pr_number,
                "body": body,
                "token": token,
                "api_base": api_base,
            }
        )
        return "updated", 55

    monkeypatch.setattr("ai_risk_manager.cli.upsert_pr_comment", _fake_upsert)

    code = main(
        [
            "publish-pr-comment",
            "--repo",
            "owner/repo",
            "--pr-number",
            "12",
            "--summary-file",
            str(summary),
        ]
    )

    assert code == 0
    assert captured["repo_full_name"] == "owner/repo"
    assert captured["pr_number"] == 12
    assert captured["token"] == "secret"
    output = capsys.readouterr().out
    assert "PR comment updated." in output
