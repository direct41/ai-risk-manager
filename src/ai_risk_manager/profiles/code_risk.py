from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ai_risk_manager.collectors.plugins.base import ArtifactBundle, CollectorPlugin
from ai_risk_manager.collectors.plugins.registry import get_plugin_for_stack
from ai_risk_manager.collectors.plugins.universal_artifacts import collect_universal_artifacts
from ai_risk_manager.profiles.base import ProfileApplicability, ProfileId
from ai_risk_manager.schemas.types import (
    AppliedSupportLevel,
    AnalysisEngine,
    CompetitiveMode,
    PreflightResult,
    RepositorySupportState,
    RunContext,
    SupportLevel,
)
from ai_risk_manager.signals.adapters import artifact_bundle_to_signal_bundle
from ai_risk_manager.signals.types import SignalBundle
from ai_risk_manager.stacks.discovery import StackDetectionResult

DEFAULT_SUPPORT_LEVEL_BY_STACK: dict[str, AppliedSupportLevel] = {
    "fastapi_pytest": "l2",
    "django_drf": "l2",
    "express_node": "l2",
    "unknown": "l0",
}
SUPPORT_LEVEL_DOWNGRADE: dict[AppliedSupportLevel, AppliedSupportLevel] = {
    "l2": "l1",
    "l1": "l0",
    "l0": "l0",
}


def _resolve_support_level(requested: SupportLevel, detected_stack: str) -> AppliedSupportLevel:
    if requested == "auto":
        return DEFAULT_SUPPORT_LEVEL_BY_STACK.get(detected_stack, "l0")
    return requested


def _downgrade_support_level(level: AppliedSupportLevel) -> AppliedSupportLevel:
    return SUPPORT_LEVEL_DOWNGRADE[level]


def _resolve_competitive_mode(analysis_engine: AnalysisEngine) -> CompetitiveMode:
    if analysis_engine == "deterministic":
        return "deterministic"
    return "hybrid"


def _resolve_repository_support_state(
    *,
    plugin: CollectorPlugin | None,
    support_level_applied: AppliedSupportLevel,
) -> RepositorySupportState:
    if support_level_applied == "l0":
        return "partial"
    if plugin is None:
        return "unsupported"
    return "supported"


@dataclass
class CodeRiskPreparedProfile:
    profile_id: ProfileId
    applicability: ProfileApplicability
    detection: StackDetectionResult
    plugin: CollectorPlugin | None
    preflight: PreflightResult
    support_level_applied: AppliedSupportLevel
    competitive_mode: CompetitiveMode
    repository_support_state: RepositorySupportState


class CodeRiskProfile:
    profile_id: ProfileId = "code_risk"

    def prepare(
        self,
        ctx: RunContext,
        notes: list[str],
        *,
        detection: StackDetectionResult,
    ) -> tuple[CodeRiskPreparedProfile | None, int | None]:
        notes.append(f"Detected stack: {detection.stack_id} (confidence: {detection.confidence}).")
        support_level_applied = _resolve_support_level(ctx.support_level, detection.stack_id)
        competitive_mode = _resolve_competitive_mode(ctx.analysis_engine)
        if ctx.risk_policy != "balanced":
            notes.append(f"Risk policy: {ctx.risk_policy}.")

        plugin = get_plugin_for_stack(detection.stack_id)
        if plugin is None and support_level_applied != "l0":
            notes.append(f"Support level applied: {support_level_applied}.")
            notes.extend(detection.reasons)
            notes.append(f"No collector plugin is registered for stack '{detection.stack_id}'.")
            return None, 2

        if plugin is None:
            preflight = PreflightResult(
                status="WARN",
                reasons=[*detection.reasons, "Unknown stack: fallback to L0 universal risk mode."],
            )
        else:
            preflight = plugin.preflight(ctx.repo_path, probe_data=detection.probe_data)

        if preflight.status == "FAIL":
            notes.append(f"Support level applied: {support_level_applied}.")
            notes.extend(preflight.reasons)
            return None, 2
        if preflight.status == "WARN":
            notes.extend(preflight.reasons)
            if plugin is not None and ctx.support_level == "auto":
                downgraded = _downgrade_support_level(support_level_applied)
                if downgraded != support_level_applied:
                    notes.append(
                        f"Support level downgraded from {support_level_applied} to {downgraded} due to pre-flight warnings."
                    )
                    support_level_applied = downgraded

        notes.append(f"Support level applied: {support_level_applied}.")
        return (
            CodeRiskPreparedProfile(
                profile_id=self.profile_id,
                applicability="supported" if plugin is not None and support_level_applied != "l0" else "partial",
                detection=detection,
                plugin=plugin,
                preflight=preflight,
                support_level_applied=support_level_applied,
                competitive_mode=competitive_mode,
                repository_support_state=_resolve_repository_support_state(
                    plugin=plugin,
                    support_level_applied=support_level_applied,
                ),
            ),
            None,
        )

    def collect(self, prepared: CodeRiskPreparedProfile, repo_path: Path) -> tuple[ArtifactBundle, SignalBundle]:
        artifacts = collect_universal_artifacts(repo_path) if prepared.plugin is None else prepared.plugin.collect(repo_path)
        collect_signals_from_artifacts = (
            getattr(prepared.plugin, "collect_signals_from_artifacts", None) if prepared.plugin is not None else None
        )
        if callable(collect_signals_from_artifacts):
            signals = collect_signals_from_artifacts(artifacts)
        else:
            signals = artifact_bundle_to_signal_bundle(artifacts)
        return artifacts, signals


__all__ = ["CodeRiskPreparedProfile", "CodeRiskProfile"]
