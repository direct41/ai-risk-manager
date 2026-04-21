from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_risk_manager.schemas.types import (
    AnalysisEngine,
    AppliedSupportLevel,
    CIMode,
    CompetitiveMode,
    Confidence,
    GraphMode,
    RiskProfileApplicability,
    RiskProfileId,
    RepositorySupportState,
    RiskPolicy,
    Severity,
    SupportLevel,
)


class AnalyzeRequest(BaseModel):
    path: str = "."
    mode: Literal["full", "pr"] = "full"
    base: str = "main"
    no_llm: bool = True
    provider: Literal["auto", "api", "cli"] = "auto"
    baseline_graph: str | None = None
    output_dir: str = ".riskmap"
    output_format: Literal["md", "json", "both"] = Field(default="both", alias="format")
    fail_on_severity: Severity | None = None
    suppress_file: str | None = None
    sample: bool = False
    analysis_engine: AnalysisEngine = "deterministic"
    only_new: bool = False
    min_confidence: Confidence = "low"
    ci_mode: CIMode = "advisory"
    support_level: SupportLevel = "auto"
    risk_policy: RiskPolicy = "balanced"

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class AnalyzeSummary(BaseModel):
    new_count: int
    resolved_count: int
    unchanged_count: int
    fallback_reason: str | None = None
    support_level_applied: AppliedSupportLevel
    effective_ci_mode: CIMode
    verification_pass_rate: float
    evidence_completeness: float
    competitive_mode: CompetitiveMode
    graph_mode_applied: GraphMode
    semantic_signal_count: int
    repository_support_state: RepositorySupportState
    profiles: list["AnalyzeProfileSummary"] = Field(default_factory=list)
    profile_review_focus: list[str] = Field(default_factory=list)


class AnalyzeProfileSummary(BaseModel):
    profile_id: RiskProfileId
    applicability: RiskProfileApplicability


class AnalyzeResponse(BaseModel):
    exit_code: int
    notes: list[str]
    output_dir: str
    artifacts: dict[str, str]
    result: dict[str, Any] | None
    summary: AnalyzeSummary | None = None
    correlation_id: str | None = None
    diagnostics: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
