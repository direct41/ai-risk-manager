from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ai_risk_manager.schemas.types import Confidence

SignalOrigin = Literal["deterministic", "ai"]
SignalKind = Literal[
    "ingress_surface",
    "http_write_surface",
    "test_to_ingress_coverage",
    "request_contract_binding",
    "state_transition_declared",
    "state_transition_handled_guarded",
    "test_to_endpoint_coverage",
    "dependency_version_policy",
    "side_effect_emit_contract",
    "authorization_boundary_enforced",
    "write_contract_integrity",
    "session_lifecycle_consistency",
    "html_render_safety",
    "ui_ergonomics",
]


@dataclass
class CapabilitySignal:
    id: str
    kind: SignalKind
    source_ref: str
    confidence: Confidence = "medium"
    evidence_refs: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    origin: SignalOrigin = "deterministic"


@dataclass
class SignalBundle:
    signals: list[CapabilitySignal] = field(default_factory=list)
    supported_kinds: set[SignalKind] = field(default_factory=set)
