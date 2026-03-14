from __future__ import annotations

from pathlib import Path
from typing import Literal, cast

from ai_risk_manager.collectors.plugins.base import ArtifactBundle, StackProbeResult
from ai_risk_manager.collectors.plugins.fastapi_artifacts import (
    FastAPISignals,
    collect_fastapi_artifacts,
    scan_fastapi_signals,
)
from ai_risk_manager.collectors.plugins.sdk import CapabilitySignalPluginMixin
from ai_risk_manager.schemas.types import Confidence, PreflightResult


def _probe_reasons(signals: FastAPISignals) -> list[str]:
    reasons: list[str] = []
    if signals.has_fastapi_import:
        reasons.append("Detected FastAPI import patterns.")
    if signals.has_router:
        reasons.append("Detected FastAPI router decorator patterns.")
    if signals.has_pytest:
        reasons.append("Detected pytest import patterns.")
    return reasons


def _preflight_from_signals(signals: FastAPISignals) -> PreflightResult:
    reasons: list[str] = []
    if not signals.has_fastapi_import and not signals.has_router:
        reasons.append("FastAPI patterns were not found (imports/routes missing).")
        return PreflightResult(status="FAIL", reasons=reasons)

    if not signals.has_pytest:
        reasons.append("pytest patterns were not found; test coverage recommendations may be noisy.")
        return PreflightResult(status="WARN", reasons=reasons)

    return PreflightResult(status="PASS", reasons=[])


class FastAPICollectorPlugin(CapabilitySignalPluginMixin):
    stack_id: Literal["fastapi_pytest"] = "fastapi_pytest"
    supported_signal_kinds = {
        "ingress_surface",
        "http_write_surface",
        "test_to_ingress_coverage",
        "request_contract_binding",
        "state_transition_declared",
        "state_transition_handled_guarded",
        "test_to_endpoint_coverage",
        "dependency_version_policy",
        "write_contract_integrity",
        "session_lifecycle_consistency",
        "generated_test_quality",
        "workflow_automation_risk",
    }
    unsupported_signal_kinds = {
        "side_effect_emit_contract",
        "authorization_boundary_enforced",
        "html_render_safety",
        "ui_ergonomics",
    }

    def probe(self, repo_path: Path) -> StackProbeResult | None:
        signals = scan_fastapi_signals(repo_path)
        if not signals.has_fastapi_import and not signals.has_router:
            return None

        confidence = cast(Confidence, "high" if signals.has_fastapi_import and signals.has_router else "medium")
        reasons = _probe_reasons(signals)
        if not signals.has_pytest:
            reasons.append("pytest patterns were not detected.")

        return StackProbeResult(
            stack_id=self.stack_id,
            confidence=confidence,
            reasons=reasons,
            probe_data=signals,
        )

    def preflight(self, repo_path: Path, probe_data: object | None = None) -> PreflightResult:
        signals = probe_data if isinstance(probe_data, FastAPISignals) else scan_fastapi_signals(repo_path)
        return _preflight_from_signals(signals)

    def collect(self, repo_path: Path) -> ArtifactBundle:
        return collect_fastapi_artifacts(repo_path)


__all__ = ["FastAPISignals", "FastAPICollectorPlugin", "scan_fastapi_signals"]
