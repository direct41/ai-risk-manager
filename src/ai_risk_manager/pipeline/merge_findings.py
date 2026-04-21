from __future__ import annotations

from dataclasses import replace
import hashlib
from typing import cast

from ai_risk_manager.schemas.types import Confidence, Finding, FindingsReport, FindingOrigin

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}
CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}


def _normalize_source_ref(source_ref: str) -> str:
    parts = source_ref.rsplit(":", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return source_ref


def ensure_fingerprint(finding: Finding) -> Finding:
    if finding.fingerprint:
        return finding
    base = "|".join(
        [
            finding.rule_id,
            _normalize_source_ref(finding.source_ref),
            finding.title.strip().lower(),
            finding.origin,
        ]
    )
    fingerprint = hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]
    return replace(finding, fingerprint=fingerprint)


def _meets_min_confidence(confidence: Confidence, min_confidence: Confidence) -> bool:
    return CONFIDENCE_RANK[confidence] >= CONFIDENCE_RANK[min_confidence]


def _merge_two(current: Finding, incoming: Finding) -> Finding:
    winner = current
    loser = incoming
    if SEVERITY_RANK[incoming.severity] > SEVERITY_RANK[current.severity]:
        winner = incoming
        loser = current

    merged_confidence = (
        winner.confidence
        if CONFIDENCE_RANK[winner.confidence] >= CONFIDENCE_RANK[loser.confidence]
        else loser.confidence
    )
    merged_refs = sorted(set(winner.evidence_refs + loser.evidence_refs))
    merged_origin = cast(FindingOrigin, "ai" if "ai" in {winner.origin, loser.origin} else "deterministic")
    merged_generated_without_llm = winner.generated_without_llm and loser.generated_without_llm
    return replace(
        winner,
        confidence=merged_confidence,
        origin=merged_origin,
        generated_without_llm=merged_generated_without_llm,
        evidence_refs=merged_refs,
    )


def merge_findings(
    deterministic_findings: FindingsReport,
    ai_findings: FindingsReport,
    *,
    min_confidence: Confidence,
    top_limit: int = 20,
) -> FindingsReport:
    by_fingerprint: dict[str, Finding] = {}

    for source in (deterministic_findings.findings, ai_findings.findings):
        for finding in source:
            normalized = ensure_fingerprint(finding)
            if not normalized.evidence_refs and normalized.source_ref and normalized.origin == "deterministic":
                normalized = replace(normalized, evidence_refs=[normalized.source_ref])
            key = normalized.fingerprint
            if key in by_fingerprint:
                by_fingerprint[key] = _merge_two(by_fingerprint[key], normalized)
            else:
                by_fingerprint[key] = normalized

    merged = [
        finding
        for finding in by_fingerprint.values()
        if finding.evidence_refs and _meets_min_confidence(finding.confidence, min_confidence)
    ]
    merged.sort(
        key=lambda f: (
            -SEVERITY_RANK.get(f.severity, 0),
            -CONFIDENCE_RANK.get(f.confidence, 0),
            f.rule_id,
        )
    )
    if ai_findings.findings:
        merged = merged[:top_limit]

    generated_without_llm = all(f.generated_without_llm for f in merged) if merged else True
    return FindingsReport(findings=merged, generated_without_llm=generated_without_llm)
