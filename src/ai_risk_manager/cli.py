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
    analyze.add_argument("--output-dir", default=".riskmap", help="Output directory")

    return parser


def _run_analyze(args: argparse.Namespace) -> int:
    repo_path = Path(args.path).resolve()
    output_dir = Path(args.output_dir).resolve()

    ctx = RunContext(
        repo_path=repo_path,
        mode=args.mode,
        base=args.base if args.mode == "pr" else None,
        output_dir=output_dir,
        provider=args.provider,
        no_llm=args.no_llm,
    )

    result, exit_code, notes = run_pipeline(ctx)
    if result is None and exit_code == 2:
        print("Pre-flight FAIL: repository is unsupported for MVP (expected FastAPI patterns).")
        for note in notes:
            print(f"- {note}")
        return 2

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


if __name__ == "__main__":
    raise SystemExit(main())
