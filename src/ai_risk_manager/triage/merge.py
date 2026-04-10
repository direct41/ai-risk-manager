from __future__ import annotations

from dataclasses import replace

from ai_risk_manager.schemas.types import (
    AnalysisScope,
    CIMode,
    Confidence,
    Finding,
    FindingsReport,
    MergeDecision,
    MergeTriage,
    MergeTriageAction,
    RepositorySupportState,
    RunSummary,
    Severity,
    TestPlan,
    TestRecommendation,
)

SEVERITY_WEIGHT: dict[Severity, int] = {
    "critical": 40,
    "high": 25,
    "medium": 12,
    "low": 4,
}
CONFIDENCE_WEIGHT: dict[Confidence, int] = {
    "high": 12,
    "medium": 6,
    "low": 0,
}
STATUS_WEIGHT = {
    "new": 18,
    "unchanged": 4,
    "resolved": -20,
}
ACTION_LIMIT = 5
TRIAGE_BUDGET_MINUTES = 10


def _finding_score(finding: Finding) -> int:
    score = SEVERITY_WEIGHT.get(finding.severity, 0)
    score += CONFIDENCE_WEIGHT.get(finding.confidence, 0)
    score += STATUS_WEIGHT.get(finding.status, 0)
    if finding.evidence_refs:
        score += min(8, len(finding.evidence_refs) * 2)
    if finding.origin == "ai":
        score -= 4
    return max(0, score)


def _rank_findings(findings: list[Finding]) -> list[Finding]:
    return sorted(
        findings,
        key=lambda finding: (
            -_finding_score(finding),
            -SEVERITY_WEIGHT.get(finding.severity, 0),
            -CONFIDENCE_WEIGHT.get(finding.confidence, 0),
            finding.rule_id,
        ),
    )


def _test_plan_by_finding(test_plan: TestPlan) -> dict[str, TestRecommendation]:
    by_finding: dict[str, TestRecommendation] = {}
    for item in test_plan.items:
        by_finding.setdefault(item.finding_id, item)
    return by_finding


def _estimated_minutes(finding: Finding, item: TestRecommendation | None) -> int:
    if finding.severity in {"critical", "high"}:
        return 5
    if item and item.test_type in {"integration", "e2e"}:
        return 4
    return 3


def _action_for_finding(
    finding: Finding,
    item: TestRecommendation | None,
    *,
    rank: int,
) -> MergeTriageAction:
    if item is None:
        return MergeTriageAction(
            id=f"merge-triage:{rank}:{finding.id}",
            finding_id=finding.id,
            rule_id=finding.rule_id,
            title=finding.title,
            priority=finding.severity,
            confidence=finding.confidence,
            status=finding.status,
            source_ref=finding.source_ref,
            action=finding.recommendation,
            rationale=(
                f"Ranked by release-risk score `{_finding_score(finding)}` from severity, confidence, "
                "PR status, and evidence refs."
            ),
            estimated_minutes=_estimated_minutes(finding, item),
        )

    return MergeTriageAction(
        id=f"merge-triage:{rank}:{finding.id}",
        finding_id=finding.id,
        rule_id=finding.rule_id,
        title=finding.title,
        priority=finding.severity,
        confidence=finding.confidence,
        status=finding.status,
        source_ref=finding.source_ref,
        action=item.recommendation,
        rationale=(
            f"Add this test first because it addresses `{finding.rule_id}` with "
            f"`{finding.severity}` severity and `{finding.status}` PR status."
        ),
        estimated_minutes=_estimated_minutes(finding, item),
        test_type=item.test_type,
        test_target=item.test_target,
        assertions=list(item.assertions),
    )


def _budgeted_actions(findings: list[Finding], test_plan: TestPlan) -> list[MergeTriageAction]:
    recommendations = _test_plan_by_finding(test_plan)
    actions: list[MergeTriageAction] = []
    spent = 0
    for rank, finding in enumerate(_rank_findings(findings), start=1):
        item = recommendations.get(finding.id)
        action = _action_for_finding(finding, item, rank=rank)
        if actions and spent + action.estimated_minutes > TRIAGE_BUDGET_MINUTES:
            continue
        actions.append(action)
        spent += action.estimated_minutes
        if len(actions) >= ACTION_LIMIT:
            break
    return actions


def _risk_score(findings: list[Finding]) -> int:
    top_scores = [_finding_score(finding) for finding in _rank_findings(findings)[:ACTION_LIMIT]]
    return min(100, sum(top_scores))


def _resolve_decision(
    findings: list[Finding],
    *,
    analysis_scope: AnalysisScope,
    repository_support_state: RepositorySupportState,
    effective_ci_mode: CIMode,
) -> MergeDecision:
    if any(
        finding.status == "new" and finding.severity == "critical" and finding.confidence == "high"
        for finding in findings
    ):
        return "block_recommended"

    if effective_ci_mode == "soft" and any(
        finding.status == "new" and finding.severity in {"critical", "high"} for finding in findings
    ):
        return "block_recommended"

    if analysis_scope == "full_fallback" and any(finding.severity in {"critical", "high"} for finding in findings):
        return "review_required"

    if analysis_scope == "full" and any(finding.severity in {"critical", "high"} for finding in findings):
        return "review_required"

    if repository_support_state != "supported" and findings:
        return "review_required"

    if any(finding.status == "new" and finding.severity in {"critical", "high"} for finding in findings):
        return "review_required"

    if any(finding.status == "new" and finding.severity == "medium" for finding in findings):
        return "review_required"

    return "ready"


def _decision_headline(decision: MergeDecision, risk_score: int, actions: list[MergeTriageAction]) -> str:
    if decision == "block_recommended":
        return f"Do not merge before handling the top release-risk action(s); risk score `{risk_score}`."
    if decision == "review_required":
        return f"Run a focused 10-minute risk review before merge; risk score `{risk_score}`."
    if actions:
        return f"No blocking release-risk signal; optional cleanup remains, risk score `{risk_score}`."
    return "No active release-risk action detected for the current scope."


def _decision_reasons(
    findings: list[Finding],
    *,
    analysis_scope: AnalysisScope,
    repository_support_state: RepositorySupportState,
    summary: RunSummary,
) -> list[str]:
    reasons: list[str] = []
    new_high_or_critical = [
        finding for finding in findings if finding.status == "new" and finding.severity in {"critical", "high"}
    ]
    if new_high_or_critical:
        reasons.append(f"{len(new_high_or_critical)} new high/critical release-risk finding(s) in current scope.")
    if analysis_scope == "full_fallback":
        reasons.append("PR impact mapping fell back to full scan, so changed-file risk attribution is weaker.")
    if analysis_scope == "full" and any(finding.severity in {"critical", "high"} for finding in findings):
        reasons.append("Full repository scan found high/critical release-risk signals.")
    if repository_support_state != "supported":
        reasons.append(f"Repository support state is `{repository_support_state}`, so findings should stay advisory.")
    if summary.evidence_completeness < 1.0:
        reasons.append(f"Evidence completeness is `{summary.evidence_completeness:.0%}`.")
    if summary.verification_pass_rate < 1.0:
        reasons.append(f"Verification pass rate is `{summary.verification_pass_rate:.0%}`.")
    if not findings:
        reasons.append("No findings survived evidence, policy, suppression, and confidence filters.")
    return reasons


def build_merge_triage(
    findings: FindingsReport,
    test_plan: TestPlan,
    *,
    summary: RunSummary,
    analysis_scope: AnalysisScope,
) -> MergeTriage:
    ranked = _rank_findings(findings.findings)
    actions = _budgeted_actions(ranked, test_plan)
    risk_score = _risk_score(ranked)
    new_high_or_critical_count = sum(
        1 for finding in findings.findings if finding.status == "new" and finding.severity in {"critical", "high"}
    )
    decision = _resolve_decision(
        findings.findings,
        analysis_scope=analysis_scope,
        repository_support_state=summary.repository_support_state,
        effective_ci_mode=summary.effective_ci_mode,
    )
    estimated_minutes = min(TRIAGE_BUDGET_MINUTES, sum(action.estimated_minutes for action in actions))

    return MergeTriage(
        decision=decision,
        headline=_decision_headline(decision, risk_score, actions),
        risk_score=risk_score,
        estimated_triage_minutes=estimated_minutes,
        top_risk_count=len(actions),
        new_high_or_critical_count=new_high_or_critical_count,
        verification_pass_rate=summary.verification_pass_rate,
        evidence_completeness=summary.evidence_completeness,
        reasons=_decision_reasons(
            findings.findings,
            analysis_scope=analysis_scope,
            repository_support_state=summary.repository_support_state,
            summary=summary,
        ),
        actions=actions,
        generated_without_llm=findings.generated_without_llm and test_plan.generated_without_llm,
    )


def _clone_action_for_markdown(action: MergeTriageAction) -> MergeTriageAction:
    assertions = [assertion.strip() for assertion in action.assertions if assertion.strip()]
    return replace(action, assertions=assertions[:3])


def render_merge_triage_md(triage: MergeTriage) -> str:
    lines: list[str] = []
    lines.append("# Merge Risk Triage")
    lines.append("")
    lines.append(f"- Decision: `{triage.decision}`")
    lines.append(f"- Headline: {triage.headline}")
    lines.append(f"- Risk score: `{triage.risk_score}/100`")
    lines.append(f"- 10-minute triage budget used: `{triage.estimated_triage_minutes} min`")
    lines.append(f"- New high/critical findings: `{triage.new_high_or_critical_count}`")
    lines.append(f"- Evidence completeness: `{triage.evidence_completeness:.0%}`")
    lines.append(f"- Verification pass rate: `{triage.verification_pass_rate:.0%}`")

    lines.append("")
    lines.append("## Why")
    lines.append("")
    if triage.reasons:
        for reason in triage.reasons:
            lines.append(f"- {reason}")
    else:
        lines.append("- No additional triage reason.")

    lines.append("")
    lines.append("## Test First")
    lines.append("")
    if not triage.actions:
        lines.append("No immediate test or fix action required.")
    else:
        for idx, raw_action in enumerate(triage.actions, start=1):
            action = _clone_action_for_markdown(raw_action)
            lines.append(
                f"{idx}. [{action.priority}] `{action.rule_id}` at `{action.source_ref}` "
                f"({action.estimated_minutes} min)"
            )
            lines.append(f"   Action: {action.action}")
            lines.append(f"   Why first: {action.rationale}")
            if action.test_target:
                lines.append(f"   Test target: `{action.test_target}`")
            for assertion in action.assertions:
                lines.append(f"   Assertion: {assertion}")

    return "\n".join(lines).strip() + "\n"
