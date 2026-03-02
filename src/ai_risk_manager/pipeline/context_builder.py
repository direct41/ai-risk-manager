from __future__ import annotations

from pathlib import Path

from ai_risk_manager.schemas.types import RunContext


def normalize_cli_choice(value: str) -> str:
    return value.replace("-", "_")


def build_run_context(
    *,
    repo_path: Path,
    mode: str,
    base: str | None,
    output_dir: Path,
    provider: str,
    no_llm: bool,
    output_format: str = "both",
    fail_on_severity: str | None = None,
    suppress_file: Path | None = None,
    baseline_graph: Path | None = None,
    analysis_engine: str = "ai_first",
    only_new: bool = False,
    min_confidence: str = "low",
    ci_mode: str = "advisory",
    support_level: str = "auto",
    risk_policy: str = "balanced",
) -> RunContext:
    return RunContext(
        repo_path=repo_path,
        mode=mode,  # type: ignore[arg-type]
        base=base if mode == "pr" else None,
        output_dir=output_dir,
        provider=provider,  # type: ignore[arg-type]
        no_llm=no_llm,
        output_format=output_format,  # type: ignore[arg-type]
        fail_on_severity=fail_on_severity,  # type: ignore[arg-type]
        suppress_file=suppress_file,
        baseline_graph=baseline_graph,
        analysis_engine=analysis_engine,  # type: ignore[arg-type]
        only_new=only_new,
        min_confidence=min_confidence,  # type: ignore[arg-type]
        ci_mode=ci_mode,  # type: ignore[arg-type]
        support_level=support_level,  # type: ignore[arg-type]
        risk_policy=risk_policy,  # type: ignore[arg-type]
    )
