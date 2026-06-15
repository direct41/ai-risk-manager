from __future__ import annotations

import json
from pathlib import Path

from ai_risk_manager.cli import main
from ai_risk_manager.integrations.github_pr_review import (
    GitHubPRMetadata,
    GitHubPRReference,
    GitHubPRReviewError,
    fetch_github_pr_evidence,
    parse_github_pr_url,
    prepare_github_pr_checkout,
)


def test_parse_github_pr_url_accepts_canonical_url() -> None:
    ref = parse_github_pr_url("https://github.com/example/project/pull/123")

    assert ref.repo_full_name == "example/project"
    assert ref.pr_number == 123
    assert ref.clone_url == "https://github.com/example/project.git"


def test_parse_github_pr_url_rejects_non_github_url() -> None:
    try:
        parse_github_pr_url("https://example.com/example/project/pull/123")
    except GitHubPRReviewError as exc:
        assert str(exc) == "review-pr expects an https://github.com/<owner>/<repo>/pull/<number> URL."
    else:
        raise AssertionError("Expected GitHubPRReviewError")


def test_prepare_github_pr_checkout_uses_explicit_pull_and_base_sha(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[list[str], Path | None]] = []

    def _fake_run_git(args: list[str], *, cwd: Path | None = None, timeout: int = 120) -> None:
        calls.append((args, cwd))

    monkeypatch.setattr("ai_risk_manager.integrations.github_pr_review._run_git", _fake_run_git)
    ref = GitHubPRReference(
        repo_full_name="example/project",
        pr_number=123,
        clone_url="https://github.com/example/project.git",
    )

    checkout = prepare_github_pr_checkout(
        ref,
        base_ref="release/v1",
        base_sha="a" * 40,
        workspace=tmp_path,
    )

    assert checkout == tmp_path / "example-project-pull-123"
    assert calls[0][0] == [
        "clone",
        "--no-tags",
        "--depth=100",
        "--no-checkout",
        "https://github.com/example/project.git",
        str(checkout),
    ]
    assert "refs/pull/123/head:refs/heads/airisk-pr-123" in calls[1][0]
    assert "a" * 40 in calls[1][0]
    assert "refs/heads/release/v1:refs/remotes/origin/release/v1" not in calls[1][0]
    assert calls[2][0] == ["checkout", "--detach", "airisk-pr-123"]


def test_prepare_github_pr_checkout_uses_base_ref_without_base_sha(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[list[str], Path | None]] = []

    def _fake_run_git(args: list[str], *, cwd: Path | None = None, timeout: int = 120) -> None:
        calls.append((args, cwd))

    monkeypatch.setattr("ai_risk_manager.integrations.github_pr_review._run_git", _fake_run_git)
    ref = GitHubPRReference(
        repo_full_name="example/project",
        pr_number=123,
        clone_url="https://github.com/example/project.git",
    )

    prepare_github_pr_checkout(
        ref,
        base_ref="release/v1",
        workspace=tmp_path,
    )

    assert "refs/heads/release/v1:refs/remotes/origin/release/v1" in calls[1][0]
    assert "refs/pull/123/head:refs/heads/airisk-pr-123" in calls[1][0]


def test_prepare_github_pr_checkout_rejects_option_like_base(tmp_path: Path) -> None:
    ref = GitHubPRReference(
        repo_full_name="example/project",
        pr_number=123,
        clone_url="https://github.com/example/project.git",
    )

    try:
        prepare_github_pr_checkout(ref, base_ref="--upload-pack=bad", workspace=tmp_path)
    except GitHubPRReviewError as exc:
        assert "Unsafe Git ref" in str(exc)
    else:
        raise AssertionError("Expected GitHubPRReviewError")


def test_fetch_github_pr_evidence_normalizes_files_and_marks_truncation(monkeypatch) -> None:
    responses: list[object] = [
        {
            "title": "Fix behavior",
            "body": "Details",
            "state": "open",
            "changed_files": 2,
            "base": {"ref": "main"},
            "head": {"sha": "abcdef"},
        },
        [
            {
                "filename": "app.py",
                "status": "modified",
                "additions": 3,
                "deletions": 1,
                "patch": "123456",
            }
        ],
    ]

    def _fake_read(url: str, *, headers: dict[str, str]) -> object:
        assert headers["User-Agent"] == "ai-risk-manager"
        return responses.pop(0)

    monkeypatch.setattr("ai_risk_manager.integrations.github_pr_review._read_github_json", _fake_read)

    evidence = fetch_github_pr_evidence(
        GitHubPRReference(
            repo_full_name="example/project",
            pr_number=123,
            clone_url="https://github.com/example/project.git",
        ),
        max_patch_chars=4,
    )

    assert evidence.title == "Fix behavior"
    assert evidence.files[0].patch == "1234"
    assert evidence.files_truncated is True
    assert evidence.patches_truncated is True


def test_cli_review_pr_builds_context_from_github_pr_url(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    captured: dict[str, object] = {}
    pipeline_contexts = []
    checkout_refs: list[str] = []

    def _fake_fetch(ref: GitHubPRReference, *, token: str = "", api_base: str = "https://api.github.com"):
        captured["metadata_ref"] = ref
        captured["token"] = token
        captured["api_base"] = api_base
        return GitHubPRMetadata(base_ref="develop", base_sha="a" * 40, head_sha="b" * 40)

    def _fake_prepare(
        ref: GitHubPRReference,
        *,
        base_ref: str,
        base_sha: str | None = None,
        workspace: Path,
    ) -> Path:
        captured["checkout_ref"] = ref
        captured["base_ref"] = base_ref
        captured["base_sha"] = base_sha
        captured["workspace_exists"] = workspace.exists()
        return checkout

    def _fake_checkout_ref(repo_path: Path, ref: str) -> None:
        assert repo_path == checkout
        checkout_refs.append(ref)

    def _fake_run_pipeline(ctx):
        pipeline_contexts.append(ctx)
        captured["ctx"] = ctx
        return object(), 0, ["resolved 1 changed file"]

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    monkeypatch.setattr("ai_risk_manager.cli.fetch_github_pr_metadata", _fake_fetch)
    monkeypatch.setattr("ai_risk_manager.cli.prepare_github_pr_checkout", _fake_prepare)
    monkeypatch.setattr("ai_risk_manager.cli.checkout_git_ref", _fake_checkout_ref)
    monkeypatch.setattr("ai_risk_manager.cli.run_pipeline", _fake_run_pipeline)

    code = main(["review-pr", "https://github.com/example/project/pull/123"])

    assert code == 0
    baseline_ctx = pipeline_contexts[0]
    ctx = captured["ctx"]
    assert baseline_ctx.mode == "full"
    assert baseline_ctx.output_dir == tmp_path / ".riskmap" / "review-pr-example-project-123" / "baseline"
    assert ctx.repo_path == checkout
    assert ctx.mode == "pr"
    assert ctx.base == "a" * 40
    assert ctx.baseline_graph == tmp_path / ".riskmap" / "review-pr-example-project-123" / "baseline" / "graph.json"
    assert ctx.no_llm is True
    assert ctx.output_dir == tmp_path / ".riskmap" / "review-pr-example-project-123"
    assert captured["token"] == "secret"
    assert captured["base_sha"] == "a" * 40
    assert captured["workspace_exists"] is True
    assert checkout_refs == ["a" * 40, "airisk-pr-123"]
    output = capsys.readouterr().out
    assert "PR review completed." in output
    assert "merge_triage.md" in output
    metadata = json.loads(
        (tmp_path / ".riskmap" / "review-pr-example-project-123" / "review_pr_metadata.json").read_text(
            encoding="utf-8"
        )
    )
    assert metadata["base_sha"] == "a" * 40
    assert metadata["head_sha"] == "b" * 40
