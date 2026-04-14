from __future__ import annotations

from collections import Counter
from pathlib import Path

from ai_risk_manager.schemas.types import (
    GitHubCheckPayload,
    PRSummary,
    PRSummaryAction,
    PRSummaryFinding,
    FindingsReport,
    PipelineResult,
)

SEVERITY_ORDER = "critical high medium low".split()
CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}
SEVERITY_INDEX = {severity: idx for idx, severity in enumerate(SEVERITY_ORDER)}
_REVIEW_FOCUS_BY_RULE = {
    "critical_path_no_tests": "Add or update targeted regression tests for the changed critical path before merge.",
    "missing_transition_handler": "Review state transitions and confirm handler coverage for changed lifecycle paths.",
    "broken_invariant_on_transition": "Review state guards and invariant enforcement around changed transition logic.",
    "dependency_risk_policy_violation": "Review dependency pinning and runtime drift before merge.",
    "pr_code_change_without_test_delta": "Expand regression coverage for the changed application code before merge.",
    "pr_dependency_change_without_test_delta": "Review dependency drift and validate changed runtime behavior with focused tests.",
    "pr_contract_change_without_test_delta": "Check schema compatibility and update consumer or integration coverage around contract changes.",
    "pr_migration_change_without_test_delta": "Review migration compatibility, rollback path, and data safety before merge.",
    "pr_runtime_config_change_requires_review": "Review deployment and runtime configuration assumptions before merge.",
    "pr_auth_boundary_change_requires_review": "Review authn/authz boundaries and negative-path coverage around the changed area.",
    "pr_payment_boundary_change_requires_review": "Review payment safety, idempotency, and failure handling in the changed area.",
    "pr_admin_surface_change_requires_review": "Review privileged actions and authorization scope in the changed admin surface.",
    "pr_workflow_change_requires_review": "Review CI automation trust boundaries, permissions, and rollout behavior.",
    "workflow_untrusted_context_to_shell": "Check automation trust boundaries and shell interpolation handling.",
    "workflow_external_action_not_pinned": "Review automation supply-chain controls and immutable action pinning.",
    "agent_generated_test_missing_negative_path": "Add negative-path coverage for changed write or validation flows.",
    "agent_generated_test_nondeterministic_dependency": "Stabilize flaky tests before relying on them in merge decisions.",
}


def _summary_counts(findings: FindingsReport) -> dict[str, int]:
    counts = Counter(f.severity for f in findings.findings)
    return {
        "critical": counts.get("critical", 0),
        "high": counts.get("high", 0),
        "medium": counts.get("medium", 0),
        "low": counts.get("low", 0),
    }


def _rank_findings(findings):
    return sorted(
        findings,
        key=lambda f: (
            SEVERITY_INDEX.get(f.severity, len(SEVERITY_ORDER)),
            CONFIDENCE_ORDER.get(f.confidence, 3),
            -len(f.evidence_refs),
            f.rule_id,
        ),
    )


def _review_focus(findings) -> list[str]:
    focus: list[str] = []
    seen: set[str] = set()
    for finding in _rank_findings(findings):
        message = _REVIEW_FOCUS_BY_RULE.get(finding.rule_id)
        if not message or message in seen:
            continue
        focus.append(message)
        seen.add(message)
        if len(focus) >= 3:
            break
    return focus


def _suppression_hints(findings) -> list[str]:
    hints: list[str] = []
    seen: set[str] = set()
    for finding in _rank_findings(findings):
        key = finding.suppression_key.strip()
        if not key or key in seen:
            continue
        hints.append(key)
        seen.add(key)
        if len(hints) >= 4:
            break
    return hints


def render_report_md(result: PipelineResult, notes: list[str]) -> str:
    counts = _summary_counts(result.findings)

    lines: list[str] = []
    lines.append("# Risk Analysis Report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|---|---:|")
    for sev in ("critical", "high", "medium", "low"):
        lines.append(f"| {sev} | {counts[sev]} |")

    lines.append("")
    lines.append("## Run Metadata")
    lines.append("")
    lines.append(f"- Pre-flight status: `{result.preflight.status}`")
    if result.preflight.reasons:
        for reason in result.preflight.reasons:
            lines.append(f"- Pre-flight note: {reason}")
    lines.append(f"- analysis_scope: `{result.analysis_scope}`")
    lines.append(f"- support_level_applied: `{result.summary.support_level_applied}`")
    lines.append(f"- repository_support_state: `{result.summary.repository_support_state}`")
    lines.append(f"- effective_ci_mode: `{result.summary.effective_ci_mode}`")
    lines.append(f"- competitive_mode: `{result.summary.competitive_mode}`")
    lines.append(f"- graph_mode_applied: `{result.summary.graph_mode_applied}`")
    lines.append(f"- semantic_signal_count: `{result.summary.semantic_signal_count}`")
    lines.append(
        f"- PR delta: new=`{result.summary.new_count}`, resolved=`{result.summary.resolved_count}`, unchanged=`{result.summary.unchanged_count}`"
    )
    if result.summary.fallback_reason:
        lines.append(f"- fallback_reason: `{result.summary.fallback_reason}`")
    lines.append(f"- Data Quality (low-confidence ratio): `{result.data_quality_low_confidence_ratio:.2%}`")
    lines.append(f"- Graph Statistics (analysis): `{len(result.graph.nodes)} nodes`, `{len(result.graph.edges)} edges`")
    lines.append(
        "- Graph Statistics (deterministic): "
        f"`{len(result.deterministic_graph.nodes)} nodes`, `{len(result.deterministic_graph.edges)} edges`"
    )
    lines.append(f"- Suppressed findings: `{result.suppressed_count}`")
    lines.append(f"- Run metric (precision proxy): `{result.run_metrics.precision_proxy:.2%}`")
    lines.append(f"- Run metric (actionability proxy): `{result.run_metrics.actionability_proxy:.2%}`")
    lines.append(f"- Run metric (verification pass rate): `{result.summary.verification_pass_rate:.2%}`")
    lines.append(f"- Run metric (evidence completeness): `{result.summary.evidence_completeness:.2%}`")
    lines.append(f"- Run metric (triage time proxy): `{result.run_metrics.triage_time_proxy_min:.1f} min`")
    lines.append(f"- Duration: `{result.run_metrics.duration_ms} ms`")
    for note in notes:
        lines.append(f"- Provider note: {note}")

    lines.append("")
    lines.append("## Merge Triage")
    lines.append("")
    lines.append(f"- Decision: `{result.merge_triage.decision}`")
    lines.append(f"- Headline: {result.merge_triage.headline}")
    lines.append(f"- Risk score: `{result.merge_triage.risk_score}/100`")
    lines.append(f"- 10-minute triage budget used: `{result.merge_triage.estimated_triage_minutes} min`")
    if result.merge_triage.reasons:
        for reason in result.merge_triage.reasons[:3]:
            lines.append(f"- Reason: {reason}")

    lines.append("")
    lines.append("## Why This Matters for Release Risk")
    lines.append("")
    if not result.findings.findings:
        lines.append("No high-signal release risks detected in current scope.")
    else:
        top_severity = sorted(
            result.findings.findings,
            key=lambda f: SEVERITY_INDEX.get(f.severity, len(SEVERITY_ORDER)),
        )[0].severity
        lines.append(
            f"Detected `{len(result.findings.findings)}` active risk(s). "
            f"Highest severity is `{top_severity}`, which can impact release confidence if ignored."
        )

    lines.append("")
    lines.append("## Top Actions for Next Sprint")
    lines.append("")
    if not result.findings.findings:
        lines.append("No immediate actions required.")
    else:
        actions = _rank_findings(result.findings.findings)[:5]
        for finding in actions:
            lines.append(f"- Action: {finding.recommendation}")
            lines.append(f"  Expected impact: reduce `{finding.rule_id}` risk around `{finding.source_ref}`.")

    lines.append("")
    lines.append("## Top Risks")
    lines.append("")
    if not result.findings.findings:
        lines.append("No risks detected in current scope.")
    else:
        top = _rank_findings(result.findings.findings)[:5]
        for finding in top:
            lines.append(f"### {finding.title}")
            lines.append(f"- Severity: `{finding.severity}`")
            lines.append(f"- Confidence: `{finding.confidence}`")
            lines.append(f"- Evidence refs: `{len(finding.evidence_refs)}`")
            lines.append(f"- Status: `{finding.status}`")
            lines.append(f"- Origin: `{finding.origin}`")
            lines.append(f"- Source: `{finding.source_ref}`")
            lines.append(f"- Why: {finding.description}")
            lines.append(f"- Action: {finding.recommendation}")
            lines.append(f"- Suppress key: `{finding.suppression_key}`")
            lines.append("- To ignore, add to `.airiskignore`:")
            lines.append(f"  - `key: \"{finding.suppression_key}\"`")
            lines.append("")

    lines.append("## Findings")
    lines.append("")
    for finding in result.findings.findings:
        lines.append(
            f"- [{finding.severity}] [{finding.status}] `{finding.rule_id}` at `{finding.source_ref}`: {finding.title}"
        )

    lines.append("")
    lines.append("## Recommended Test Strategy")
    lines.append("")
    if not result.test_plan.items:
        lines.append("No additional test recommendations.")
    else:
        for item in result.test_plan.items:
            lines.append(f"- [{item.priority}] {item.recommendation} (source: `{item.source_ref}`)")

    lines.append("")
    lines.append("## 10-Minute Test-First Order")
    lines.append("")
    if not result.merge_triage.actions:
        lines.append("No immediate test-first action required.")
    else:
        for action in result.merge_triage.actions:
            lines.append(
                f"- [{action.priority}] `{action.rule_id}` at `{action.source_ref}` "
                f"({action.estimated_minutes} min): {action.action}"
            )

    return "\n".join(lines).strip() + "\n"


def write_report(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_pr_summary(result: PipelineResult, notes: list[str], *, only_new: bool = False) -> PRSummary:
    top_candidates = result.findings.findings
    if only_new:
        min_rank = SEVERITY_INDEX["high"]
        top_candidates = [
            finding
            for finding in top_candidates
            if finding.status == "new" and SEVERITY_INDEX.get(finding.severity, len(SEVERITY_ORDER)) <= min_rank
        ]

    top_findings = [
        PRSummaryFinding(
            rule_id=finding.rule_id,
            title=finding.title,
            severity=finding.severity,
            confidence=finding.confidence,
            status=finding.status,
            source_ref=finding.source_ref,
            recommendation=finding.recommendation,
            evidence_ref_count=len(finding.evidence_refs),
            suppression_key=finding.suppression_key,
        )
        for finding in _rank_findings(top_candidates)[:5]
    ]
    top_actions = [
        PRSummaryAction(
            rule_id=action.rule_id,
            priority=action.priority,
            source_ref=action.source_ref,
            action=action.action,
            estimated_minutes=action.estimated_minutes,
        )
        for action in result.merge_triage.actions[:3]
    ]
    return PRSummary(
        marker="ai-risk-manager",
        decision=result.merge_triage.decision,
        headline=result.merge_triage.headline,
        risk_score=result.merge_triage.risk_score,
        analysis_scope=result.analysis_scope,
        support_level_applied=result.summary.support_level_applied,
        repository_support_state=result.summary.repository_support_state,
        effective_ci_mode=result.summary.effective_ci_mode,
        findings_count=len(result.findings.findings),
        new_count=result.summary.new_count,
        resolved_count=result.summary.resolved_count,
        unchanged_count=result.summary.unchanged_count,
        fallback_reason=result.summary.fallback_reason,
        reasons=list(result.merge_triage.reasons[:3]),
        review_focus=_review_focus(top_candidates),
        suppression_hints=_suppression_hints(top_candidates),
        notes=list(notes),
        top_findings=top_findings,
        top_actions=top_actions,
    )


def render_pr_summary_md(summary: PRSummary) -> str:
    marker = f"<!-- {summary.marker} -->"
    lines = [marker, "## AI Risk Manager", ""]
    lines.append(f"- Decision: `{summary.decision}`")
    lines.append(f"- Headline: {summary.headline}")
    lines.append(f"- Risk score: `{summary.risk_score}/100`")
    lines.append(f"- Scope: `{summary.analysis_scope}`")
    lines.append(
        f"- PR delta: new=`{summary.new_count}`, resolved=`{summary.resolved_count}`, unchanged=`{summary.unchanged_count}`"
    )
    lines.append(
        f"- Support: `{summary.support_level_applied}` / `{summary.repository_support_state}` / ci=`{summary.effective_ci_mode}`"
    )
    if summary.fallback_reason:
        lines.append(f"- Fallback: `{summary.fallback_reason}`")
    lines.append("")

    if summary.reasons:
        lines.append("### Why Review")
        lines.append("")
        for reason in summary.reasons:
            lines.append(f"- {reason}")
        lines.append("")

    if summary.review_focus:
        lines.append("### Review Focus")
        lines.append("")
        for item in summary.review_focus:
            lines.append(f"- {item}")
        lines.append("")

    lines.append("### Top Risks")
    lines.append("")
    if not summary.top_findings:
        lines.append("No findings in current PR scope.")
    else:
        for finding in summary.top_findings:
            lines.append(
                f"- [{finding.severity}] [{finding.status}] `{finding.rule_id}` at `{finding.source_ref}`: "
                f"{finding.title}. Action: {finding.recommendation}"
            )
    lines.append("")
    if summary.suppression_hints:
        lines.append("### Suppression Hints")
        lines.append("")
        lines.append("If a finding is intentional, add one of these entries to `.airiskignore`:")
        lines.append("")
        lines.append("```yaml")
        for key in summary.suppression_hints:
            lines.append(f'- key: "{key}"')
        lines.append("```")
        lines.append("")
    lines.append("### Test First")
    lines.append("")
    if not summary.top_actions:
        lines.append("No immediate test-first action required.")
    else:
        for action in summary.top_actions:
            lines.append(
                f"- [{action.priority}] `{action.rule_id}` at `{action.source_ref}` "
                f"({action.estimated_minutes} min): {action.action}"
            )
    lines.append("")
    lines.append("Full details: see `pr_summary.json`, `merge_triage.md`, `report.md`, `findings.json`, and `test_plan.json`.")
    return "\n".join(lines).strip() + "\n"


def build_github_check_payload(summary: PRSummary) -> GitHubCheckPayload:
    if summary.decision == "block_recommended":
        conclusion = "action_required"
    elif summary.decision == "review_required":
        conclusion = "neutral"
    else:
        conclusion = "success"

    short_lines = [
        f"Decision: {summary.decision}",
        f"Risk score: {summary.risk_score}/100",
        f"Scope: {summary.analysis_scope}",
        f"PR delta: new={summary.new_count}, resolved={summary.resolved_count}, unchanged={summary.unchanged_count}",
    ]
    if summary.review_focus:
        short_lines.append(f"Review focus: {summary.review_focus[0]}")
    if summary.top_findings:
        short_lines.append(
            "Top risk: "
            f"{summary.top_findings[0].rule_id} at {summary.top_findings[0].source_ref}"
        )
    text = render_pr_summary_md(summary)
    return GitHubCheckPayload(
        name="AI Risk Manager",
        conclusion=conclusion,
        title=summary.headline,
        summary="\n".join(short_lines),
        text=text,
    )
