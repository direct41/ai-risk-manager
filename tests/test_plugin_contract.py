from __future__ import annotations

from pathlib import Path
from typing import cast

from ai_risk_manager.collectors.plugins.base import ArtifactBundle, CollectorPlugin, StackProbeResult
from ai_risk_manager.collectors.plugins.contract import (
    ALL_SIGNAL_KINDS,
    PLUGIN_CONTRACT_VERSION,
    evaluate_plugin_conformance,
)
from ai_risk_manager.collectors.plugins.registry import evaluate_registered_plugin_conformance
from ai_risk_manager.schemas.types import PreflightResult


class _BrokenPlugin:
    stack_id = "unknown"
    plugin_contract_version = "0"
    target_support_level = "l1"
    supported_signal_kinds = {"dependency_version_policy"}
    unsupported_signal_kinds = {"http_write_surface"}

    def probe(self, repo_path: Path) -> StackProbeResult | None:
        return None

    def preflight(self, repo_path: Path, probe_data: object | None = None) -> PreflightResult:
        return PreflightResult(status="PASS", reasons=[])

    def collect(self, repo_path: Path) -> ArtifactBundle:
        return ArtifactBundle()


def test_registered_plugins_pass_contract_conformance() -> None:
    reports = evaluate_registered_plugin_conformance()
    assert reports
    assert all(report.plugin_contract_version == PLUGIN_CONTRACT_VERSION for report in reports)
    assert all(report.passed for report in reports)


def test_conformance_report_contains_full_capability_matrix() -> None:
    report = evaluate_registered_plugin_conformance()[0]
    assert set(report.capability_matrix.keys()) == set(ALL_SIGNAL_KINDS)
    assert any(status == "unsupported" for status in report.capability_matrix.values())


def test_conformance_detects_missing_required_l1_capabilities() -> None:
    report = evaluate_plugin_conformance(cast(CollectorPlugin, _BrokenPlugin()))
    assert report.passed is False
    assert any("plugin_contract_version mismatch" in err for err in report.errors)
    assert any("Missing required supported capabilities for l1" in err for err in report.errors)
    assert any("cannot be marked unsupported" in err for err in report.errors)

