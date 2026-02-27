from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal
import json

Severity = Literal["critical", "high", "medium", "low"]
Confidence = Literal["high", "medium", "low"]
Layer = Literal["domain", "infrastructure", "qa"]
FindingOrigin = Literal["deterministic", "ai"]
FindingStatus = Literal["new", "resolved", "unchanged"]
AnalysisEngine = Literal["deterministic", "hybrid", "ai_first"]
CIMode = Literal["advisory", "soft", "block_new_critical"]
SupportLevel = Literal["auto", "l0", "l1", "l2"]
AppliedSupportLevel = Literal["l0", "l1", "l2"]
RiskPolicy = Literal["conservative", "balanced", "aggressive"]
CompetitiveMode = Literal["deterministic", "hybrid"]
TestType = Literal["api", "integration", "unit", "e2e"]
PreflightStatus = Literal["PASS", "WARN", "FAIL"]
AnalysisScope = Literal["impacted", "full", "full_fallback"]


@dataclass
class Node:
    id: str
    type: str
    name: str
    layer: Layer
    source_ref: str
    confidence: Confidence = "medium"
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Edge:
    id: str
    source_node_id: str
    target_node_id: str
    type: str
    source_ref: str
    evidence: str
    confidence: Confidence = "medium"
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Graph:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    declared_transitions: list["TransitionSpec"] = field(default_factory=list)
    handled_transitions: list["TransitionSpec"] = field(default_factory=list)


@dataclass
class TransitionSpec:
    machine: str
    source: str
    target: str
    source_ref: str
    line: int | None = None
    snippet: str = ""
    invariant_guarded: bool = True


@dataclass
class Finding:
    id: str
    rule_id: str
    title: str
    description: str
    severity: Severity
    confidence: Confidence
    evidence: str
    source_ref: str
    suppression_key: str
    recommendation: str
    origin: FindingOrigin = "deterministic"
    fingerprint: str = ""
    status: FindingStatus = "unchanged"
    evidence_refs: list[str] = field(default_factory=list)
    generated_without_llm: bool = False


@dataclass
class FindingsReport:
    findings: list[Finding] = field(default_factory=list)
    generated_without_llm: bool = False


@dataclass
class TestRecommendation:
    id: str
    title: str
    priority: Severity
    finding_id: str
    source_ref: str
    recommendation: str
    test_type: TestType = "api"
    test_target: str = ""
    assertions: list[str] = field(default_factory=list)
    confidence: Confidence = "medium"
    generated_without_llm: bool = False


@dataclass
class TestPlan:
    items: list[TestRecommendation] = field(default_factory=list)
    generated_without_llm: bool = False


@dataclass
class PreflightResult:
    status: PreflightStatus
    reasons: list[str] = field(default_factory=list)


@dataclass
class RunContext:
    repo_path: Path
    mode: Literal["full", "pr"]
    base: str | None
    output_dir: Path
    provider: Literal["auto", "api", "cli"]
    no_llm: bool
    output_format: Literal["md", "json", "both"] = "both"
    fail_on_severity: Severity | None = None
    suppress_file: Path | None = None
    baseline_graph: Path | None = None
    analysis_engine: AnalysisEngine = "ai_first"
    only_new: bool = False
    min_confidence: Confidence = "low"
    ci_mode: CIMode = "advisory"
    support_level: SupportLevel = "auto"
    risk_policy: RiskPolicy = "balanced"


@dataclass
class RunSummary:
    new_count: int = 0
    resolved_count: int = 0
    unchanged_count: int = 0
    fallback_reason: str | None = None
    support_level_applied: AppliedSupportLevel = "l0"
    verification_pass_rate: float = 0.0
    evidence_completeness: float = 0.0
    competitive_mode: CompetitiveMode = "deterministic"


@dataclass
class RunMetrics:
    precision_proxy: float
    fallback_reason: str | None
    new_findings_count: int
    actionability_proxy: float
    triage_time_proxy_min: float
    verification_pass_rate: float
    evidence_completeness: float
    support_level_applied: AppliedSupportLevel
    competitive_mode: CompetitiveMode
    analysis_scope: AnalysisScope
    duration_ms: int


@dataclass
class PipelineResult:
    preflight: PreflightResult
    analysis_scope: AnalysisScope
    data_quality_low_confidence_ratio: float
    suppressed_count: int
    graph: Graph
    findings_raw: FindingsReport
    findings: FindingsReport
    test_plan: TestPlan
    summary: RunSummary
    run_metrics: RunMetrics


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def to_dict(instance: Any) -> Any:
    return asdict(instance)
