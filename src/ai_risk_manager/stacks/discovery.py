from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ai_risk_manager.collectors.plugins.base import DetectionConfidence, StackId, StackProbeResult
from ai_risk_manager.collectors.plugins.registry import list_plugins

_CONFIDENCE_RANK: dict[DetectionConfidence, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
}


@dataclass
class StackDetectionResult:
    stack_id: StackId
    confidence: DetectionConfidence
    reasons: list[str] = field(default_factory=list)
    probe_data: object | None = None


def detect_stack(repo_path: Path) -> StackDetectionResult:
    best_probe: StackProbeResult | None = None
    for plugin in list_plugins():
        probe = plugin.probe(repo_path)
        if probe is None:
            continue
        if best_probe is None or _CONFIDENCE_RANK[probe.confidence] > _CONFIDENCE_RANK[best_probe.confidence]:
            best_probe = probe

    if best_probe is None:
        return StackDetectionResult(
            stack_id="unknown",
            confidence="low",
            reasons=["No supported stack signals were detected."],
        )

    return StackDetectionResult(
        stack_id=best_probe.stack_id,
        confidence=best_probe.confidence,
        reasons=best_probe.reasons,
        probe_data=best_probe.probe_data,
    )
