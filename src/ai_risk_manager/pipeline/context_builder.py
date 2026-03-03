from __future__ import annotations

from pathlib import Path
from typing import Literal, cast

from ai_risk_manager.schemas.types import AnalysisEngine, CIMode, Confidence, RiskPolicy, RunContext, Severity, SupportLevel


def normalize_cli_choice(value: str) -> str:
    return value.replace("-", "_")


Mode = Literal["full", "pr"]
Provider = Literal["auto", "api", "cli"]
OutputFormat = Literal["md", "json", "both"]

_MODE_CHOICES = {"full", "pr"}
_PROVIDER_CHOICES = {"auto", "api", "cli"}
_OUTPUT_FORMAT_CHOICES = {"md", "json", "both"}
_ANALYSIS_ENGINE_CHOICES = {"deterministic", "hybrid", "ai_first"}
_CONFIDENCE_CHOICES = {"high", "medium", "low"}
_CI_MODE_CHOICES = {"advisory", "soft", "block_new_critical"}
_SUPPORT_LEVEL_CHOICES = {"auto", "l0", "l1", "l2"}
_RISK_POLICY_CHOICES = {"conservative", "balanced", "aggressive"}
_SEVERITY_CHOICES = {"critical", "high", "medium", "low"}


def _parse_choice(value: str, choices: set[str], *, field: str) -> str:
    if value not in choices:
        allowed = ", ".join(sorted(choices))
        raise ValueError(f"Invalid value for {field}: {value!r}. Allowed: {allowed}.")
    return value


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
    mode_value = cast(Mode, _parse_choice(mode, _MODE_CHOICES, field="mode"))
    provider_value = cast(Provider, _parse_choice(provider, _PROVIDER_CHOICES, field="provider"))
    output_format_value = cast(OutputFormat, _parse_choice(output_format, _OUTPUT_FORMAT_CHOICES, field="output_format"))
    analysis_engine_value = cast(
        AnalysisEngine, _parse_choice(analysis_engine, _ANALYSIS_ENGINE_CHOICES, field="analysis_engine")
    )
    min_confidence_value = cast(Confidence, _parse_choice(min_confidence, _CONFIDENCE_CHOICES, field="min_confidence"))
    ci_mode_value = cast(CIMode, _parse_choice(ci_mode, _CI_MODE_CHOICES, field="ci_mode"))
    support_level_value = cast(
        SupportLevel, _parse_choice(support_level, _SUPPORT_LEVEL_CHOICES, field="support_level")
    )
    risk_policy_value = cast(RiskPolicy, _parse_choice(risk_policy, _RISK_POLICY_CHOICES, field="risk_policy"))
    fail_on_severity_value: Severity | None = None
    if fail_on_severity is not None:
        fail_on_severity_value = cast(
            Severity, _parse_choice(fail_on_severity, _SEVERITY_CHOICES, field="fail_on_severity")
        )

    return RunContext(
        repo_path=repo_path,
        mode=mode_value,
        base=base if mode_value == "pr" else None,
        output_dir=output_dir,
        provider=provider_value,
        no_llm=no_llm,
        output_format=output_format_value,
        fail_on_severity=fail_on_severity_value,
        suppress_file=suppress_file,
        baseline_graph=baseline_graph,
        analysis_engine=analysis_engine_value,
        only_new=only_new,
        min_confidence=min_confidence_value,
        ci_mode=ci_mode_value,
        support_level=support_level_value,
        risk_policy=risk_policy_value,
    )
