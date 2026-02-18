from __future__ import annotations

import argparse
from pathlib import Path

from ai_risk_manager.pipeline.run import run_pipeline
from ai_risk_manager.schemas.types import RunContext


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

    return parser


def _resolve_sample_repo() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "eval" / "repos" / "milestone2_fastapi"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("Bundled sample repository not found")


def _run_analyze(args: argparse.Namespace) -> int:
    if args.sample:
        repo_path = _resolve_sample_repo().resolve()
    else:
        repo_path = Path(args.path).resolve()
    output_dir = Path(args.output_dir).resolve()
    baseline_graph = Path(args.baseline_graph).resolve() if args.baseline_graph else None
    suppress_file = Path(args.suppress_file).resolve() if args.suppress_file else None

    ctx = RunContext(
        repo_path=repo_path,
        mode=args.mode,
        base=args.base if args.mode == "pr" else None,
        output_dir=output_dir,
        provider=args.provider,
        no_llm=args.no_llm,
        output_format=args.format,
        fail_on_severity=args.fail_on_severity,
        suppress_file=suppress_file,
        baseline_graph=baseline_graph,
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


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "analyze":
        return _run_analyze(args)

    parser.print_help()
    return 2


def app() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    app()
