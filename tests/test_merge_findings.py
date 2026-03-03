from __future__ import annotations

from typing import cast

from ai_risk_manager.pipeline.merge_findings import ensure_fingerprint, merge_findings
from ai_risk_manager.schemas.types import Confidence, Finding, FindingOrigin, FindingsReport, Severity


def _finding(
    *,
    fid: str,
    rule_id: str = "critical_path_no_tests",
    title: str = "Missing tests",
    severity: str = "high",
    confidence: str = "medium",
    source_ref: str = "app/api.py:10",
    origin: str = "deterministic",
    evidence_refs: list[str] | None = None,
) -> Finding:
    return Finding(
        id=fid,
        rule_id=rule_id,
        title=title,
        description="d",
        severity=cast(Severity, severity),
        confidence=cast(Confidence, confidence),
        evidence="e",
        source_ref=source_ref,
        suppression_key=fid,
        recommendation="add tests",
        origin=cast(FindingOrigin, origin),
        evidence_refs=[source_ref] if evidence_refs is None else evidence_refs,
    )


def test_merge_deduplicates_by_fingerprint_and_picks_highest_severity() -> None:
    deterministic = ensure_fingerprint(_finding(fid="d1", severity="high", origin="deterministic"))
    ai = ensure_fingerprint(_finding(fid="a1", severity="critical", origin="ai"))
    ai = Finding(**{**ai.__dict__, "fingerprint": deterministic.fingerprint})

    merged = merge_findings(
        FindingsReport(findings=[deterministic], generated_without_llm=True),
        FindingsReport(findings=[ai], generated_without_llm=False),
        min_confidence="low",
        top_limit=20,
    )
    assert len(merged.findings) == 1
    assert merged.findings[0].severity == "critical"
    assert merged.findings[0].origin == "ai"


def test_merge_drops_findings_without_evidence_refs() -> None:
    ai = _finding(fid="a2", origin="ai", evidence_refs=[])
    merged = merge_findings(
        FindingsReport(findings=[], generated_without_llm=True),
        FindingsReport(findings=[ai], generated_without_llm=False),
        min_confidence="low",
        top_limit=20,
    )
    assert not merged.findings
