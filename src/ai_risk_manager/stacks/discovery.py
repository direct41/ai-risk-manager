from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ai_risk_manager.collectors.plugins.base import StackId
from ai_risk_manager.collectors.plugins.fastapi import scan_fastapi_signals

DetectionConfidence = Literal["high", "medium", "low"]


@dataclass
class StackDetectionResult:
    stack_id: StackId
    confidence: DetectionConfidence
    reasons: list[str] = field(default_factory=list)


def detect_stack(repo_path: Path) -> StackDetectionResult:
    signals = scan_fastapi_signals(repo_path)
    reasons: list[str] = []

    if signals.has_fastapi_import:
        reasons.append("Detected FastAPI import patterns.")
    if signals.has_router:
        reasons.append("Detected FastAPI router decorator patterns.")
    if signals.has_pytest:
        reasons.append("Detected pytest import patterns.")

    if signals.has_fastapi_import and signals.has_router:
        if not signals.has_pytest:
            reasons.append("pytest patterns were not detected.")
        return StackDetectionResult(stack_id="fastapi_pytest", confidence="high", reasons=reasons)

    if signals.has_fastapi_import or signals.has_router:
        if not signals.has_pytest:
            reasons.append("pytest patterns were not detected.")
        return StackDetectionResult(stack_id="fastapi_pytest", confidence="medium", reasons=reasons)

    reasons.append("FastAPI stack signals were not detected.")
    return StackDetectionResult(stack_id="unknown", confidence="low", reasons=reasons)
