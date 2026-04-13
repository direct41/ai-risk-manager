from __future__ import annotations

from ai_risk_manager.schemas.types import (
    Finding,
    FindingsReport,
    RunSummary,
    TestPlan as RiskTestPlan,
    TestRecommendation as RiskTestRecommendation,
)
from ai_risk_manager.triage.merge import build_merge_triage, render_merge_triage_md


def _finding(
    finding_id: str,
    *,
    severity: str,
    status: str = "new",
    confidence: str = "medium",
    rule_id: str = "critical_path_no_tests",
) -> Finding:
    return Finding(
        id=finding_id,
        rule_id=rule_id,
        title=f"Finding {finding_id}",
        description="Risk description",
        severity=severity,
        confidence=confidence,
        evidence="Evidence",
        source_ref=f"app/{finding_id}.py:10",
        suppression_key=finding_id,
        recommendation=f"Add coverage for {finding_id}",
        status=status,
        evidence_refs=[f"app/{finding_id}.py:10"],
        generated_without_llm=True,
    )


def test_merge_triage_prioritizes_new_high_risks_within_ten_minutes() -> None:
    high = _finding("pay_order", severity="high", confidence="high")
    medium = _finding("send_invoice", severity="medium")
    low = _finding("settings", severity="low", status="unchanged")
    test_plan = RiskTestPlan(
        items=[
            RiskTestRecommendation(
                id="test-plan:pay_order",
                title="Cover payment",
                priority="high",
                finding_id=high.id,
                source_ref=high.source_ref,
                recommendation="Add success and failure payment tests",
                test_type="api",
                test_target="POST /orders/{id}/pay",
                assertions=["Payment succeeds.", "Invalid state is rejected."],
                generated_without_llm=True,
            ),
            RiskTestRecommendation(
                id="test-plan:send_invoice",
                title="Cover invoice",
                priority="medium",
                finding_id=medium.id,
                source_ref=medium.source_ref,
                recommendation="Add invoice side-effect test",
                test_type="integration",
                test_target="invoice worker",
                assertions=["Invoice event is emitted."],
                generated_without_llm=True,
            ),
            RiskTestRecommendation(
                id="test-plan:settings",
                title="Cover settings",
                priority="low",
                finding_id=low.id,
                source_ref=low.source_ref,
                recommendation="Add settings smoke test",
                test_type="unit",
                test_target="settings",
                assertions=["Settings parse."],
                generated_without_llm=True,
            ),
        ],
        generated_without_llm=True,
    )

    triage = build_merge_triage(
        FindingsReport(findings=[low, medium, high], generated_without_llm=True),
        test_plan,
        summary=RunSummary(verification_pass_rate=1.0, evidence_completeness=1.0),
        analysis_scope="impacted",
    )

    assert triage.decision == "review_required"
    assert triage.estimated_triage_minutes <= 10
    assert triage.actions[0].finding_id == high.id
    assert triage.actions[0].test_target == "POST /orders/{id}/pay"
    assert triage.new_high_or_critical_count == 1


def test_merge_triage_soft_ci_recommends_block_for_new_high_risk() -> None:
    finding = _finding("create_order", severity="high", confidence="medium")

    triage = build_merge_triage(
        FindingsReport(findings=[finding], generated_without_llm=True),
        RiskTestPlan(generated_without_llm=True),
        summary=RunSummary(
            effective_ci_mode="soft",
            verification_pass_rate=1.0,
            evidence_completeness=1.0,
        ),
        analysis_scope="impacted",
    )

    assert triage.decision == "block_recommended"
    assert "Do not merge" in triage.headline


def test_merge_triage_full_scan_requires_review_for_high_risk() -> None:
    finding = _finding("legacy_checkout", severity="high", confidence="medium", status="unchanged")

    triage = build_merge_triage(
        FindingsReport(findings=[finding], generated_without_llm=True),
        RiskTestPlan(generated_without_llm=True),
        summary=RunSummary(verification_pass_rate=1.0, evidence_completeness=1.0),
        analysis_scope="full",
    )

    assert triage.decision == "review_required"
    assert any("Full repository scan" in reason for reason in triage.reasons)


def test_merge_triage_markdown_explains_test_first_order() -> None:
    finding = _finding("create_order", severity="high", confidence="high")
    triage = build_merge_triage(
        FindingsReport(findings=[finding], generated_without_llm=True),
        RiskTestPlan(generated_without_llm=True),
        summary=RunSummary(verification_pass_rate=1.0, evidence_completeness=1.0),
        analysis_scope="impacted",
    )

    markdown = render_merge_triage_md(triage)

    assert "# Merge Risk Triage" in markdown
    assert "## Test First" in markdown
    assert "`critical_path_no_tests`" in markdown
