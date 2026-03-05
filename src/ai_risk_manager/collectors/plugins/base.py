from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from ai_risk_manager.schemas.types import Confidence, PreflightResult

StackId = Literal["fastapi_pytest", "django_drf", "express_node", "unknown"]
DetectionConfidence = Confidence  # backward-compatible alias


@dataclass
class StackProbeResult:
    stack_id: StackId
    confidence: DetectionConfidence
    reasons: list[str] = field(default_factory=list)
    probe_data: object | None = None


@dataclass
class ArtifactBundle:
    """Collector output consumed by graph/rule stages.

    NOTE: some fields are FastAPI-oriented in v0.1.x and may be generalized
    when additional stack plugins are introduced.
    """

    all_files: list[Path] = field(default_factory=list)
    python_files: list[Path] = field(default_factory=list)
    write_endpoints: list[tuple[str, str, str, str, int | None, str]] = field(default_factory=list)
    # (file, endpoint_name, method, route_path, line, snippet)
    endpoint_models: list[tuple[str, str, str]] = field(default_factory=list)  # (file, endpoint_name, model_name)
    pydantic_models: list[tuple[str, str]] = field(default_factory=list)  # (file, model_name)
    declared_transitions: list[tuple[str, str, str, str, int | None, str]] = field(default_factory=list)
    # (file, machine, src, dst, line, snippet)
    handled_transitions: list[tuple[str, str, str, str, int | None, str, bool]] = field(default_factory=list)
    # (file, machine, src, dst, line, snippet, invariant_guarded)
    test_files: list[Path] = field(default_factory=list)
    test_cases: list[tuple[str, str, int | None, str]] = field(default_factory=list)  # (file, test_name, line, snippet)
    test_http_calls: list[tuple[str, str, str, str, int | None, str]] = field(default_factory=list)
    # (file, test_name, method, route_path, line, snippet)
    dependency_specs: list[tuple[str, str, str, int | None, str | None, str]] = field(default_factory=list)
    # (file, dependency_name, raw_spec, line, policy_violation, scope)
    side_effect_requirements: list[tuple[str, str, str, str, int | None, str]] = field(default_factory=list)
    # (file, endpoint_name, effect_kind, effect_target, line, snippet)
    side_effect_emits: list[tuple[str, str, str, str, int | None, str]] = field(default_factory=list)
    # (file, emitter_name, effect_kind, effect_target, line, snippet)
    authorization_boundaries: list[tuple[str, str, str, str, int | None, str]] = field(default_factory=list)
    # (file, endpoint_name, auth_mechanism, auth_subject, line, snippet)


class CollectorPlugin(Protocol):
    @property
    def stack_id(self) -> StackId:
        ...

    def probe(self, repo_path: Path) -> StackProbeResult | None:
        ...

    def preflight(self, repo_path: Path, probe_data: object | None = None) -> PreflightResult:
        ...

    def collect(self, repo_path: Path) -> ArtifactBundle:
        ...
