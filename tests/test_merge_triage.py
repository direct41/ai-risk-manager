from __future__ import annotations

import pytest

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


def test_merge_triage_hides_unchanged_generated_test_quality_debt() -> None:
    finding = _finding(
        "legacy_test_quality",
        severity="high",
        confidence="medium",
        status="unchanged",
        rule_id="agent_generated_test_missing_negative_path",
    )

    triage = build_merge_triage(
        FindingsReport(findings=[finding], generated_without_llm=True),
        RiskTestPlan(generated_without_llm=True),
        summary=RunSummary(verification_pass_rate=1.0, evidence_completeness=1.0),
        analysis_scope="impacted",
    )

    assert triage.decision == "ready"
    assert triage.risk_score == 0
    assert triage.actions == []


def test_merge_triage_full_fallback_focuses_changed_file_findings() -> None:
    legacy_high = _finding(
        "legacy_checkout",
        severity="high",
        status="unchanged",
        rule_id="critical_path_no_tests",
    )
    unrelated_new_high = _finding(
        "schema_fixture",
        severity="high",
        status="new",
        rule_id="critical_path_no_tests",
    )
    changed_medium = _finding(
        "app/service",
        severity="medium",
        status="new",
        rule_id="pr_code_change_without_test_delta",
    )
    changed_medium.source_ref = "app/service.py"
    changed_medium.evidence_refs = ["app/service.py"]

    triage = build_merge_triage(
        FindingsReport(
            findings=[legacy_high, unrelated_new_high, changed_medium],
            generated_without_llm=True,
        ),
        RiskTestPlan(generated_without_llm=True),
        summary=RunSummary(verification_pass_rate=1.0, evidence_completeness=1.0),
        analysis_scope="full_fallback",
        changed_files={"app/service.py"},
    )

    assert triage.decision == "review_required"
    assert triage.risk_score < 100
    assert triage.new_high_or_critical_count == 0
    assert [action.finding_id for action in triage.actions] == [changed_medium.id]
    assert any("repo-wide finding(s) hidden" in reason for reason in triage.reasons)


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


@pytest.mark.parametrize(
    ("severity", "confidence", "ci_mode", "support_state", "expected_decision", "expected_score"),
    [
        ("critical", "high", "advisory", "supported", "block_recommended", 72),
        ("critical", "medium", "advisory", "supported", "review_required", 66),
        ("high", "medium", "advisory", "supported", "review_required", 51),
        ("medium", "medium", "advisory", "supported", "review_required", 38),
        ("low", "medium", "advisory", "supported", "ready", 30),
        ("high", "medium", "soft", "supported", "block_recommended", 51),
        ("low", "medium", "advisory", "partial", "review_required", 30),
    ],
)
def test_merge_triage_decision_and_score_boundaries(
    severity: str,
    confidence: str,
    ci_mode: str,
    support_state: str,
    expected_decision: str,
    expected_score: int,
) -> None:
    finding = _finding("boundary", severity=severity, confidence=confidence)

    triage = build_merge_triage(
        FindingsReport(findings=[finding], generated_without_llm=True),
        RiskTestPlan(generated_without_llm=True),
        summary=RunSummary(
            effective_ci_mode=ci_mode,
            repository_support_state=support_state,
            verification_pass_rate=1.0,
            evidence_completeness=1.0,
        ),
        analysis_scope="impacted",
    )

    assert triage.decision == expected_decision
    assert triage.risk_score == expected_score
    assert triage.estimated_triage_minutes == (5 if severity in {"critical", "high"} else 3)


def test_merge_triage_budget_and_ranking_are_exact() -> None:
    high = _finding("high", severity="high", confidence="high", rule_id="z_rule")
    medium = _finding("medium", severity="medium", confidence="medium", rule_id="a_rule")
    low = _finding("low", severity="low", confidence="medium", rule_id="b_rule")
    test_plan = RiskTestPlan(
        items=[
            RiskTestRecommendation(
                id="medium-plan",
                title="medium",
                priority="medium",
                finding_id=medium.id,
                source_ref=medium.source_ref,
                recommendation="integration test",
                test_type="integration",
                test_target="service",
            )
        ],
        generated_without_llm=True,
    )

    triage = build_merge_triage(
        FindingsReport(findings=[low, medium, high], generated_without_llm=True),
        test_plan,
        summary=RunSummary(verification_pass_rate=1.0, evidence_completeness=1.0),
        analysis_scope="impacted",
    )

    assert [action.finding_id for action in triage.actions] == ["high", "medium"]
    assert [action.estimated_minutes for action in triage.actions] == [5, 4]
    assert triage.estimated_triage_minutes == 9
    assert triage.risk_score == 100


def test_merge_triage_only_new_hides_unchanged_findings() -> None:
    unchanged = _finding("unchanged", severity="critical", confidence="high", status="unchanged")

    triage = build_merge_triage(
        FindingsReport(findings=[unchanged], generated_without_llm=True),
        RiskTestPlan(generated_without_llm=True),
        summary=RunSummary(verification_pass_rate=1.0, evidence_completeness=1.0),
        analysis_scope="impacted",
        only_new=True,
    )

    assert triage.decision == "ready"
    assert triage.risk_score == 0
    assert triage.actions == []
