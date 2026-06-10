from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile

from ai_risk_manager.integrations.github_pr_comments import GitHubCommentError, load_pr_comment_body, upsert_pr_comment
from ai_risk_manager.integrations.github_pr_review import (
    GitHubPRReviewError,
    checkout_git_ref,
    fetch_github_pr_metadata,
    parse_github_pr_url,
    prepare_github_pr_checkout,
)
from ai_risk_manager.pipeline.context_builder import build_run_context, normalize_cli_choice
from ai_risk_manager.pipeline.run import run_pipeline
from ai_risk_manager.public_pr_benchmark import (
    PublicPRBenchmarkOptions,
    inspect_public_pr_corpus,
    run_public_pr_benchmark,
)
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
        default="deterministic",
        help="Analysis strategy. Use hybrid or ai-first only when AI enrichment is explicitly intended.",
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

    review_pr = subparsers.add_parser("review-pr", help="Clone and review a public GitHub PR URL.")
    review_pr.add_argument("url", help="GitHub PR URL, for example https://github.com/owner/repo/pull/123")
    review_pr.add_argument("--base", default=None, help="Override the GitHub PR base branch")
    review_pr.add_argument(
        "--skip-baseline",
        action="store_true",
        help="Skip baseline generation on the base branch and use full_fallback PR analysis",
    )
    review_pr.add_argument("--provider", choices=["auto", "api", "cli"], default="auto", help="LLM provider")
    review_pr.add_argument(
        "--analysis-engine",
        choices=["deterministic", "hybrid", "ai-first"],
        default="deterministic",
        help="Analysis strategy. Defaults to deterministic/no-LLM for validation runs.",
    )
    review_pr.add_argument(
        "--enable-llm",
        action="store_true",
        help="Allow LLM enrichment. By default review-pr runs without sending repository snippets to an LLM.",
    )
    review_pr.add_argument("--output-dir", default=None, help="Output directory for review artifacts")
    review_pr.add_argument(
        "--format",
        choices=["md", "json", "both"],
        default="both",
        help="Output artifact format",
    )
    review_pr.set_defaults(only_new=True)
    review_pr.add_argument(
        "--include-unchanged",
        action="store_false",
        dest="only_new",
        help="Include unchanged findings in the PR summary",
    )
    review_pr.add_argument(
        "--min-confidence",
        choices=["high", "medium", "low"],
        default="low",
        help="Drop findings below confidence threshold",
    )
    review_pr.add_argument(
        "--ci-mode",
        choices=["advisory", "soft", "block-new-critical"],
        default="advisory",
        help="CI behavior for generated artifacts",
    )
    review_pr.add_argument(
        "--support-level",
        choices=["auto", "l0", "l1", "l2"],
        default="auto",
        help="Stack support maturity level",
    )
    review_pr.add_argument(
        "--risk-policy",
        choices=["conservative", "balanced", "aggressive"],
        default="balanced",
        help="Risk triage policy profile",
    )
    review_pr.add_argument(
        "--token-env",
        default="GITHUB_TOKEN",
        help="Environment variable that contains an optional GitHub token for PR metadata lookup",
    )
    review_pr.add_argument(
        "--api-base",
        default="https://api.github.com",
        help="GitHub API base URL",
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

    benchmark = subparsers.add_parser(
        "benchmark-prs",
        help="Run a public GitHub PR corpus through review-pr and evaluate expected outcomes.",
    )
    benchmark.add_argument(
        "corpus",
        nargs="?",
        default="eval/public_prs.json",
        help="Path to public PR corpus JSON.",
    )
    benchmark.add_argument(
        "--output-dir",
        default=".riskmap/public-pr-corpus",
        help="Output directory for benchmark artifacts.",
    )
    benchmark.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="Run only the selected corpus case id. May be passed multiple times.",
    )
    benchmark.add_argument("--limit", type=int, default=None, help="Run at most N corpus cases.")
    benchmark.add_argument("--skip-baseline", action="store_true", help="Pass --skip-baseline to review-pr.")
    benchmark.add_argument("--include-unchanged", action="store_true", help="Pass --include-unchanged to review-pr.")
    benchmark.add_argument("--enable-llm", action="store_true", help="Allow LLM enrichment for each review-pr run.")
    benchmark.add_argument("--provider", choices=["auto", "api", "cli"], default="auto", help="LLM provider")
    benchmark.add_argument(
        "--analysis-engine",
        choices=["deterministic", "hybrid", "ai-first"],
        default="deterministic",
        help="Analysis strategy for each review-pr run.",
    )
    benchmark.add_argument(
        "--min-confidence",
        choices=["high", "medium", "low"],
        default="low",
        help="Drop findings below confidence threshold.",
    )

    benchmark.add_argument(
        "--ci-mode",
        choices=["advisory", "soft", "block-new-critical"],
        default="advisory",
        help="CI behavior for each review-pr run.",
    )
    benchmark.add_argument(
        "--support-level",
        choices=["auto", "l0", "l1", "l2"],
        default="auto",
        help="Stack support maturity level.",
    )
    benchmark.add_argument(
        "--risk-policy",
        choices=["conservative", "balanced", "aggressive"],
        default="balanced",
        help="Risk triage policy profile.",
    )
    benchmark.add_argument(
        "--token-env",
        default="GITHUB_TOKEN",
        help="Environment variable that contains an optional GitHub token for PR metadata lookup.",
    )
    benchmark.add_argument("--api-base", default="https://api.github.com", help="GitHub API base URL.")
    benchmark.add_argument("--timeout-seconds", type=int, default=900, help="Timeout per public PR case.")

    corpus_status = subparsers.add_parser(
        "corpus-status",
        help="Validate public PR corpus labeling metadata and render the pending review queue.",
    )
    corpus_status.add_argument(
        "corpus",
        nargs="?",
        default="eval/public_prs.json",
        help="Path to public PR corpus JSON.",
    )
    corpus_status.add_argument(
        "--output-dir",
        default=".riskmap/public-pr-corpus-status",
        help="Output directory for corpus status artifacts.",
    )
    corpus_status.add_argument(
        "--strict",
        action="store_true",
        help="Return exit code 3 when labeling metadata has quality issues. Pending cases remain valid.",
    )

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
        print("Pre-flight FAIL: repository is unsupported for the selected support level.")
        print("Try --support-level auto for advisory fallback, or run on a supported app root.")
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


def _run_review_pr(args: argparse.Namespace) -> int:
    try:
        ref = parse_github_pr_url(args.url)
        metadata = fetch_github_pr_metadata(
            ref,
            token=os.getenv(args.token_env, "").strip(),
            api_base=args.api_base,
        )
    except GitHubPRReviewError as exc:
        print(f"PR review setup error: {exc}")
        return 2

    base_ref = args.base or metadata.base_ref
    owner, repo = ref.repo_full_name.split("/", 1)
    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else (Path.cwd() / ".riskmap" / f"review-pr-{owner}-{repo}-{ref.pr_number}").resolve()
    )

    try:
        with tempfile.TemporaryDirectory(prefix="riskmap-pr-") as tmp:
            repo_path = prepare_github_pr_checkout(ref, base_ref=base_ref, workspace=Path(tmp))
            baseline_graph = None
            baseline_notes: list[str] = []
            if not args.skip_baseline:
                baseline_output_dir = output_dir / "baseline"
                checkout_git_ref(repo_path, f"origin/{base_ref}")
                baseline_ctx = build_run_context(
                    repo_path=repo_path,
                    mode="full",
                    base=None,
                    output_dir=baseline_output_dir,
                    provider=args.provider,
                    no_llm=not args.enable_llm,
                    output_format="both",
                    baseline_graph=None,
                    analysis_engine=normalize_cli_choice(args.analysis_engine),
                    only_new=False,
                    min_confidence=args.min_confidence,
                    ci_mode=normalize_cli_choice(args.ci_mode),
                    support_level=args.support_level,
                    risk_policy=args.risk_policy,
                )
                baseline_result, baseline_exit_code, baseline_run_notes = run_pipeline(baseline_ctx)
                baseline_notes.extend(f"baseline: {note}" for note in baseline_run_notes)
                if baseline_result is not None and baseline_exit_code in {0, 3}:
                    baseline_graph = baseline_output_dir / "graph.json"
                    baseline_notes.append(f"Baseline artifacts written to: {baseline_output_dir}")
                else:
                    baseline_notes.append("Baseline generation failed; continuing with full_fallback PR analysis.")
                checkout_git_ref(repo_path, f"airisk-pr-{ref.pr_number}")

            ctx = build_run_context(
                repo_path=repo_path,
                mode="pr",
                base=base_ref,
                output_dir=output_dir,
                provider=args.provider,
                no_llm=not args.enable_llm,
                output_format=args.format,
                baseline_graph=baseline_graph,
                analysis_engine=normalize_cli_choice(args.analysis_engine),
                only_new=args.only_new,
                min_confidence=args.min_confidence,
                ci_mode=normalize_cli_choice(args.ci_mode),
                support_level=args.support_level,
                risk_policy=args.risk_policy,
            )
            result, exit_code, notes = run_pipeline(ctx)
            notes = baseline_notes + notes
    except (GitHubPRReviewError, ValueError) as exc:
        print(f"PR review setup error: {exc}")
        return 2

    if result is None and exit_code == 1:
        print("Provider configuration error: selected provider is unavailable.")
        for note in notes:
            print(f"- {note}")
        return 1

    if result is None and exit_code == 2:
        print("Pre-flight FAIL: repository is unsupported for the selected support level.")
        print("Try --support-level auto for advisory fallback, or run on a supported app root.")
        for note in notes:
            print(f"- {note}")
        return 2

    print(
        f"PR review completed. repo={ref.repo_full_name} pr={ref.pr_number} "
        f"base={base_ref} head={metadata.head_sha[:12]} artifacts={output_dir}"
    )
    print(f"Read first: {output_dir / 'merge_triage.md'}")
    print(f"PR summary: {output_dir / 'pr_summary.md'}")
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


def _run_benchmark_prs(args: argparse.Namespace) -> int:
    corpus_path = Path(args.corpus).resolve()
    output_dir = Path(args.output_dir).resolve()
    options = PublicPRBenchmarkOptions(
        case_ids=list(args.case_id),
        limit=args.limit,
        skip_baseline=args.skip_baseline,
        include_unchanged=args.include_unchanged,
        enable_llm=args.enable_llm,
        provider=args.provider,
        analysis_engine=args.analysis_engine,
        min_confidence=args.min_confidence,
        ci_mode=args.ci_mode,
        support_level=args.support_level,
        risk_policy=args.risk_policy,
        token_env=args.token_env,
        api_base=args.api_base,
        timeout_seconds=args.timeout_seconds,
    )
    try:
        result = run_public_pr_benchmark(corpus_path, output_dir, options=options)
    except (OSError, ValueError) as exc:
        print(f"Public PR benchmark setup error: {exc}")
        return 2

    print(
        "Public PR benchmark completed. "
        f"cases={result.total_cases} passed={result.passed_cases} "
        f"needs_human_review={result.needs_human_review_cases} failed={result.failed_cases}"
    )
    print(f"Summary: {output_dir / 'benchmark_summary.md'}")
    print(f"Machine summary: {output_dir / 'benchmark_summary.json'}")
    return 3 if result.failed_cases else 0


def _run_corpus_status(args: argparse.Namespace) -> int:
    corpus_path = Path(args.corpus).resolve()
    output_dir = Path(args.output_dir).resolve()
    try:
        result = inspect_public_pr_corpus(corpus_path, output_dir)
    except (OSError, ValueError) as exc:
        print(f"Public PR corpus setup error: {exc}")
        return 2

    print(
        "Public PR corpus status completed. "
        f"cases={result.total_cases} labeled={result.labeled_cases} "
        f"pending={result.pending_cases} issues={len(result.issues)}"
    )
    print(f"Status: {output_dir / 'corpus_status.md'}")
    print(f"Machine status: {output_dir / 'corpus_status.json'}")
    return 3 if args.strict and result.issues else 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "analyze":
        return _run_analyze(args)
    if args.command == "review-pr":
        return _run_review_pr(args)
    if args.command == "publish-pr-comment":
        return _run_publish_pr_comment(args)
    if args.command == "benchmark-prs":
        return _run_benchmark_prs(args)
    if args.command == "corpus-status":
        return _run_corpus_status(args)

    parser.print_help()
    return 2


def app() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    app()
