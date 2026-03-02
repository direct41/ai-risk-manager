from __future__ import annotations

from pathlib import Path

from ai_risk_manager.collectors.plugins.base import ArtifactBundle, StackProbeResult
from ai_risk_manager.collectors.plugins.django_artifacts import DjangoSignals, collect_django_artifacts, scan_django_signals
from ai_risk_manager.collectors.plugins.sdk import CapabilitySignalPluginMixin
from ai_risk_manager.schemas.types import PreflightResult


def _probe_reasons(signals: DjangoSignals) -> list[str]:
    reasons: list[str] = []
    if signals.has_django_import:
        reasons.append("Detected Django import patterns.")
    if signals.has_drf_import:
        reasons.append("Detected Django REST Framework import patterns.")
    if signals.has_urlpatterns:
        reasons.append("Detected Django urlpatterns.")
    if signals.has_pytest:
        reasons.append("Detected pytest patterns.")
    return reasons


def _preflight_from_signals(signals: DjangoSignals) -> PreflightResult:
    reasons: list[str] = []
    if not (signals.has_django_import or signals.has_drf_import):
        reasons.append("Django/DRF patterns were not found (imports missing).")
        return PreflightResult(status="FAIL", reasons=reasons)

    if not signals.has_urlpatterns:
        reasons.append("Django urlpatterns were not found; endpoint extraction may be incomplete.")
        return PreflightResult(status="WARN", reasons=reasons)

    if not signals.has_pytest:
        reasons.append("pytest patterns were not found; test coverage recommendations may be noisy.")
        return PreflightResult(status="WARN", reasons=reasons)

    return PreflightResult(status="PASS", reasons=[])


class DjangoCollectorPlugin(CapabilitySignalPluginMixin):
    stack_id = "django_drf"
    supported_signal_kinds = {
        "http_write_surface",
        "test_to_endpoint_coverage",
        "dependency_version_policy",
    }

    def probe(self, repo_path: Path) -> StackProbeResult | None:
        signals = scan_django_signals(repo_path)
        if not (signals.has_django_import or signals.has_drf_import or signals.has_urlpatterns):
            return None

        confidence = "high" if signals.has_django_import and signals.has_urlpatterns else "medium"
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
        signals = probe_data if isinstance(probe_data, DjangoSignals) else scan_django_signals(repo_path)
        return _preflight_from_signals(signals)

    def collect(self, repo_path: Path) -> ArtifactBundle:
        return collect_django_artifacts(repo_path)


__all__ = ["DjangoCollectorPlugin", "DjangoSignals", "scan_django_signals"]
