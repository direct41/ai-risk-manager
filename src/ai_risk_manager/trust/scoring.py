from __future__ import annotations

from pathlib import Path

from ai_risk_manager.schemas.types import Confidence, Finding, FindingTrust, RepositorySupportState, TrustBand, TrustHistorySignal
from ai_risk_manager.trust.outcomes import TrustOutcomeCounts, TrustOutcomes

_BASE_SCORE_BY_CONFIDENCE: dict[Confidence, float] = {
    "high": 0.78,
    "medium": 0.64,
    "low": 0.5,
}
_SUPPORT_DELTA_BY_STATE: dict[RepositorySupportState, float] = {
    "supported": 0.06,
    "partial": -0.04,
    "unsupported": -0.12,
}


def _resolve_ref_path_line(repo_path: Path, ref: str) -> tuple[Path, int | None]:
    line_no: int | None = None
    parts = ref.rsplit(":", 1)
    if len(parts) == 2 and parts[1].isdigit():
        ref = parts[0]
        line_no = int(parts[1])
    path = Path(ref)
    if not path.is_absolute():
        path = repo_path / path
    return path, line_no


def _ref_exists(repo_path: Path, source_ref: str) -> bool:
    path, line_no = _resolve_ref_path_line(repo_path, source_ref)
    if not path.is_file():
        return False
    if line_no is None:
        return True
    try:
        with path.open("r", encoding="utf-8") as fh:
            for idx, _ in enumerate(fh, start=1):
                if idx == line_no:
                    return True
    except OSError:
        return False
    return False


def _evidence_strength(refs: list[str], repo_path: Path) -> tuple[Confidence, int]:
    verified = sum(1 for ref in refs if _ref_exists(repo_path, ref))
    if verified >= 2:
        return "high", verified
    if verified == 1:
        return "medium", verified
    return "low", 0


def _history_signal(outcomes: TrustOutcomeCounts) -> tuple[TrustHistorySignal, float]:
    if outcomes.actioned_count > max(outcomes.accepted_count, outcomes.suppressed_count):
        return "actioned_bias", 0.05
    if outcomes.accepted_count > outcomes.suppressed_count:
        return "accepted_bias", 0.03
    if outcomes.suppressed_count > outcomes.accepted_count:
        return "suppressed_bias", -0.08
    return "neutral", 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _band(score: float) -> TrustBand:
    if score >= 0.78:
        return "strong"
    if score >= 0.6:
        return "moderate"
    return "weak"


def score_finding(
    finding: Finding,
    *,
    repo_path: Path,
    repository_support_state: RepositorySupportState,
    outcomes: TrustOutcomes,
) -> FindingTrust:
    refs = [ref for ref in finding.evidence_refs if ref]
    evidence_strength, verified_count = _evidence_strength(refs, repo_path)
    history_counts = outcomes.lookup(fingerprint=finding.fingerprint, rule_id=finding.rule_id)
    history_signal, history_delta = _history_signal(history_counts)

    score = _BASE_SCORE_BY_CONFIDENCE[finding.confidence]
    score += _SUPPORT_DELTA_BY_STATE[repository_support_state]
    score += {"high": 0.07, "medium": 0.02, "low": -0.08}[evidence_strength]
    score += 0.03 if finding.origin == "deterministic" else -0.08
    if not refs:
        score -= 0.05
    elif verified_count == 0:
        score -= 0.04
    score += history_delta
    score = _clamp(score)

    estimated_precision = _clamp(score)
    return FindingTrust(
        score=round(score, 3),
        band=_band(score),
        estimated_precision=round(estimated_precision, 3),
        evidence_strength=evidence_strength,
        history_signal=history_signal,
    )


def annotate_finding_trust(
    findings: list[Finding],
    *,
    repo_path: Path,
    repository_support_state: RepositorySupportState,
    outcomes: TrustOutcomes,
) -> list[Finding]:
    for finding in findings:
        finding.trust = score_finding(
            finding,
            repo_path=repo_path,
            repository_support_state=repository_support_state,
            outcomes=outcomes,
        )
    return findings


__all__ = ["annotate_finding_trust", "score_finding"]
