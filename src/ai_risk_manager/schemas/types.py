from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal
import json

Severity = Literal["critical", "high", "medium", "low"]
Confidence = Literal["high", "medium", "low"]
Layer = Literal["domain", "infrastructure", "qa"]


@dataclass
class Node:
    id: str
    type: str
    name: str
    layer: Layer
    source_ref: str
    confidence: Confidence = "medium"


@dataclass
class Edge:
    id: str
    source_node_id: str
    target_node_id: str
    type: str
    source_ref: str
    evidence: str
    confidence: Confidence = "medium"


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
    generated_without_llm: bool = False


@dataclass
class TestPlan:
    items: list[TestRecommendation] = field(default_factory=list)
    generated_without_llm: bool = False


@dataclass
class PreflightResult:
    status: Literal["PASS", "WARN", "FAIL"]
    reasons: list[str] = field(default_factory=list)


@dataclass
class RunContext:
    repo_path: Path
    mode: Literal["full", "pr"]
    base: str | None
    output_dir: Path
    provider: Literal["auto", "api", "cli"]
    no_llm: bool


@dataclass
class PipelineResult:
    preflight: PreflightResult
    analysis_scope: Literal["impacted", "full", "full_fallback"]
    data_quality_low_confidence_ratio: float
    graph: Graph
    findings_raw: FindingsReport
    findings: FindingsReport
    test_plan: TestPlan


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def to_dict(instance: Any) -> Any:
    return asdict(instance)
