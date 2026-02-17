from __future__ import annotations

from ai_risk_manager.schemas.types import FindingsReport, TestPlan, TestRecommendation


def generate_test_plan(
    findings: FindingsReport,
    *,
    provider: str,
    generated_without_llm: bool,
) -> TestPlan:
    items: list[TestRecommendation] = []
    for finding in findings.findings:
        items.append(
            TestRecommendation(
                id=f"test-plan:{finding.id}",
                title=f"Cover risk: {finding.rule_id}",
                priority=finding.severity,
                finding_id=finding.id,
                source_ref=finding.source_ref,
                recommendation=finding.recommendation,
                generated_without_llm=generated_without_llm,
            )
        )

    return TestPlan(items=items, generated_without_llm=generated_without_llm)
