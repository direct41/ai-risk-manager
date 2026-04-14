from __future__ import annotations

import argparse
import os
from pathlib import Path

from ai_risk_manager.integrations.github_pr_comments import GitHubCommentError, load_pr_comment_body, upsert_pr_comment
from ai_risk_manager.pipeline.context_builder import build_run_context, normalize_cli_choice
from ai_risk_manager.pipeline.run import run_pipeline
from ai_risk_manager.sample_repo import resolve_sample_repo_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="riskmap", description="AI Risk Manager CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="Analyze repository risks.")
    analyze.add_argument("path", nargs="?", default=".", help="Repository path")
    analyze.add_argument("--mode", choices=["full", "pr"], default="full", help="Analysis mode")
    analyze.add_argument("--base", default="main", help="Base branch for pr mode")
    analyze.add_argument("--no-llm", action="store_true", help="Disable LLM stages")
    analyze.add_argument("--provider", choices=["auto", "api", "cli"], default="auto", help="LLM provider")
    analyze.add_argument("--baseline-graph", default=None, help="Path to baseline graph.json for pr mode")
    analyze.add_argument("--output-dir", default=".riskmap", help="Output directory")
    analyze.add_argument("--format", choices=["md", "json", "both"], default="both", help="Output artifact format")
    analyze.add_argument(
        "--analysis-engine",
        choices=["deterministic", "hybrid", "ai-first"],
        default="ai-first",
        help="Analysis strategy. ai-first prioritizes semantic AI findings.",
    )
    analyze.add_argument("--only-new", action="store_true", help="PR summary: show only new high/critical findings")
    analyze.add_argument(
        "--min-confidence",
        choices=["high", "medium", "low"],
        default="low",
        help="Drop findings below confidence threshold",
    )
    analyze.add_argument(
        "--ci-mode",
        choices=["advisory", "soft", "block-new-critical"],
        default="advisory",
        help="CI behavior: advisory, soft-block on new high/critical, or block new critical only",
    )
    analyze.add_argument(
        "--support-level",
        choices=["auto", "l0", "l1", "l2"],
        default="auto",
        help="Stack support maturity level (auto resolves by detected stack).",
    )
    analyze.add_argument(
        "--risk-policy",
        choices=["conservative", "balanced", "aggressive"],
        default="balanced",
        help="Risk triage policy profile.",
    )
    analyze.add_argument(
        "--fail-on-severity",
        choices=["critical", "high", "medium", "low"],
        default=None,
        help="Return exit code 3 if finding severity at or above threshold exists",
    )
    analyze.add_argument("--suppress-file", default=None, help="Path to .airiskignore suppression file")
    analyze.add_argument(
        "--sample",
        action="store_true",
        help="Analyze bundled sample repo (eval/repos/milestone2_fastapi)",
    )

    publish = subparsers.add_parser("publish-pr-comment", help="Publish PR summary markdown to a GitHub PR comment.")
    publish.add_argument("--repo", required=True, help="Repository in owner/name form")
    publish.add_argument("--pr-number", required=True, type=int, help="Pull request number")
    publish.add_argument(
        "--summary-file",
        default=".riskmap/pr_summary.md",
        help="Path to generated PR summary markdown",
    )
    publish.add_argument(
        "--token-env",
        default="GITHUB_TOKEN",
        help="Environment variable that contains the GitHub token",
    )
    publish.add_argument(
        "--api-base",
        default="https://api.github.com",
        help="GitHub API base URL (for GitHub Enterprise use cases)",
    )
    publish.add_argument("--dry-run", action="store_true", help="Print the comment body instead of publishing it")

    return parser


def _run_analyze(args: argparse.Namespace) -> int:
    if args.sample:
        repo_path = resolve_sample_repo_path()
    else:
        repo_path = Path(args.path).resolve()
    output_dir = Path(args.output_dir).resolve()
    baseline_graph = Path(args.baseline_graph).resolve() if args.baseline_graph else None
    suppress_file = Path(args.suppress_file).resolve() if args.suppress_file else None

    ctx = build_run_context(
        repo_path=repo_path,
        mode=args.mode,
        base=args.base,
        output_dir=output_dir,
        provider=args.provider,
        no_llm=args.no_llm,
        output_format=args.format,
        fail_on_severity=args.fail_on_severity,
        suppress_file=suppress_file,
        baseline_graph=baseline_graph,
        analysis_engine=normalize_cli_choice(args.analysis_engine),
        only_new=args.only_new,
        min_confidence=args.min_confidence,
        ci_mode=normalize_cli_choice(args.ci_mode),
        support_level=args.support_level,
        risk_policy=args.risk_policy,
    )

    result, exit_code, notes = run_pipeline(ctx)
    if result is None and exit_code == 1:
        print("Provider configuration error: selected provider is unavailable.")
        for note in notes:
            print(f"- {note}")
        return 1

    if result is None and exit_code == 2:
        print("Pre-flight FAIL: repository is unsupported for MVP (expected FastAPI patterns).")
        for note in notes:
            print(f"- {note}")
        return 2

    if result is not None and exit_code == 3:
        print("Analysis completed with fail-on-severity threshold reached.")
        print(f"Artifacts written to: {output_dir}")
        if notes:
            print("Notes:")
            for note in notes:
                print(f"- {note}")
        return 3

    print(f"Analysis completed. Artifacts written to: {output_dir}")
    if notes:
        print("Notes:")
        for note in notes:
            print(f"- {note}")
    return exit_code


def _run_publish_pr_comment(args: argparse.Namespace) -> int:
    summary_file = Path(args.summary_file).resolve()
    try:
        body = load_pr_comment_body(summary_file)
    except GitHubCommentError as exc:
        print(f"PR comment publish error: {exc}")
        return 2

    if args.dry_run:
        print(body)
        return 0

    token = os.getenv(args.token_env, "").strip()
    if not token:
        print(f"PR comment publish error: environment variable '{args.token_env}' is empty or unset.")
        return 2

    try:
        action, comment_id = upsert_pr_comment(
            repo_full_name=args.repo,
            pr_number=args.pr_number,
            body=body,
            token=token,
            api_base=args.api_base,
        )
    except GitHubCommentError as exc:
        print(f"PR comment publish error: {exc}")
        return 2

    print(
        f"PR comment {action}. repo={args.repo} pr={args.pr_number} comment_id={comment_id} source={summary_file}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "analyze":
        return _run_analyze(args)
    if args.command == "publish-pr-comment":
        return _run_publish_pr_comment(args)

    parser.print_help()
    return 2


def app() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    app()
