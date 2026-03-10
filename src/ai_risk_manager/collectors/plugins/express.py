from __future__ import annotations

from pathlib import Path
from typing import Literal, cast

from ai_risk_manager.collectors.plugins.base import ArtifactBundle, StackProbeResult
from ai_risk_manager.collectors.plugins.express_artifacts import (
    ExpressSignals,
    collect_express_artifacts,
    scan_express_signals,
)
from ai_risk_manager.collectors.plugins.sdk import CapabilitySignalPluginMixin
from ai_risk_manager.schemas.types import Confidence, PreflightResult


def _probe_reasons(signals: ExpressSignals) -> list[str]:
    reasons: list[str] = []
    if signals.has_express_import:
        reasons.append("Detected Express import patterns.")
    if signals.has_write_routes:
        reasons.append("Detected Express write route handlers.")
    if signals.has_test_framework:
        reasons.append("Detected JavaScript test patterns.")
    return reasons


def _preflight_from_signals(signals: ExpressSignals) -> PreflightResult:
    reasons: list[str] = []
    if not signals.has_express_import and not signals.has_write_routes:
        reasons.append("Express patterns were not found (imports/routes missing).")
        return PreflightResult(status="FAIL", reasons=reasons)

    if not signals.has_write_routes:
        reasons.append("Express write routes were not detected; endpoint extraction may be incomplete.")
        return PreflightResult(status="WARN", reasons=reasons)

    if not signals.has_test_framework:
        reasons.append("JavaScript test patterns were not found; test coverage recommendations may be noisy.")
        return PreflightResult(status="WARN", reasons=reasons)

    return PreflightResult(status="PASS", reasons=[])


class ExpressCollectorPlugin(CapabilitySignalPluginMixin):
    stack_id: Literal["express_node"] = "express_node"
    supported_signal_kinds = {
        "ingress_surface",
        "http_write_surface",
        "test_to_ingress_coverage",
        "test_to_endpoint_coverage",
        "dependency_version_policy",
        "authorization_boundary_enforced",
        "write_contract_integrity",
        "session_lifecycle_consistency",
        "html_render_safety",
        "ui_ergonomics",
    }
    unsupported_signal_kinds = {
        "request_contract_binding",
        "state_transition_declared",
        "state_transition_handled_guarded",
        "side_effect_emit_contract",
    }

    def probe(self, repo_path: Path) -> StackProbeResult | None:
        signals = scan_express_signals(repo_path)
        if not signals.has_express_import and not signals.has_write_routes:
            return None

        confidence = cast(Confidence, "high" if signals.has_express_import and signals.has_write_routes else "medium")
        reasons = _probe_reasons(signals)
        if not signals.has_test_framework:
            reasons.append("JavaScript test patterns were not detected.")

        return StackProbeResult(
            stack_id=self.stack_id,
            confidence=confidence,
            reasons=reasons,
            probe_data=signals,
        )

    def preflight(self, repo_path: Path, probe_data: object | None = None) -> PreflightResult:
        signals = probe_data if isinstance(probe_data, ExpressSignals) else scan_express_signals(repo_path)
        return _preflight_from_signals(signals)

    def collect(self, repo_path: Path) -> ArtifactBundle:
        return collect_express_artifacts(repo_path)


__all__ = ["ExpressCollectorPlugin", "ExpressSignals", "scan_express_signals"]
