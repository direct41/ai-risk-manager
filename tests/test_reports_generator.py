from __future__ import annotations

from ai_risk_manager.reports.generator import build_pr_summary
from ai_risk_manager.schemas.types import (
    Finding,
    FindingsReport,
    Graph,
    MergeTriage,
    PipelineResult,
    PreflightResult,
    RunMetrics,
    RunSummary,
    Severity,
    TestPlan as RiskTestPlan,
)


def _finding(
    rule_id: str,
    source_ref: str,
    *,
    severity: Severity = "high",
    evidence_refs: list[str] | None = None,
) -> Finding:
    return Finding(
        id=f"{rule_id}:{source_ref}",
        rule_id=rule_id,
        title=f"{rule_id} title",
        description="desc",
        severity=severity,
        confidence="medium",
        evidence="evidence",
        source_ref=source_ref,
        suppression_key=f"{rule_id}:{source_ref}",
        recommendation=f"fix {rule_id}",
        evidence_refs=evidence_refs or [source_ref],
        status="new",
        generated_without_llm=True,
    )


def _result(findings: list[Finding]) -> PipelineResult:
    summary = RunSummary(
        new_count=len(findings),
        support_level_applied="l1",
        repository_support_state="supported",
        effective_ci_mode="advisory",
    )
    return PipelineResult(
        preflight=PreflightResult(status="PASS"),
        analysis_scope="full_fallback",
        data_quality_low_confidence_ratio=0.0,
        suppressed_count=0,
        graph=Graph(),
        deterministic_graph=Graph(),
        findings_raw=FindingsReport(findings=findings, generated_without_llm=True),
        findings=FindingsReport(findings=findings, generated_without_llm=True),
        test_plan=RiskTestPlan(generated_without_llm=True),
        merge_triage=MergeTriage(
            decision="review_required",
            headline="Review required",
            risk_score=80,
            estimated_triage_minutes=4,
            top_risk_count=len(findings),
            new_high_or_critical_count=1,
            verification_pass_rate=1.0,
            evidence_completeness=1.0,
        ),
        summary=summary,
        run_metrics=RunMetrics(
            precision_proxy=1.0,
            fallback_reason=None,
            new_findings_count=len(findings),
            actionability_proxy=1.0,
            triage_time_proxy_min=4.0,
            verification_pass_rate=1.0,
            evidence_completeness=1.0,
            support_level_applied="l1",
            competitive_mode="deterministic",
            analysis_scope="full_fallback",
            duration_ms=1,
        ),
    )


def test_pr_summary_prioritizes_changed_scope_rule_over_repo_wide_risk() -> None:
    repo_wide = _finding("critical_path_no_tests", "server/app.js:48", severity="high")
    changed_scope = _finding("pr_code_change_without_test_delta", "public/app.js", severity="medium")

    summary = build_pr_summary(_result([repo_wide, changed_scope]), [], changed_files={"public/app.js"})

    assert summary.top_findings[0].rule_id == "pr_code_change_without_test_delta"
    assert summary.top_actions[0].rule_id == "pr_code_change_without_test_delta"
    assert summary.changed_files == ["public/app.js"]


def test_pr_summary_prioritizes_source_ref_matching_changed_file() -> None:
    repo_wide = _finding("dependency_risk_policy_violation", "package.json:8", severity="high")
    changed_scope = _finding("stored_xss_unsafe_innerhtml", "public/app.js:12", severity="medium")

    summary = build_pr_summary(_result([repo_wide, changed_scope]), [], changed_files={"public/app.js"})

    assert summary.top_findings[0].rule_id == "stored_xss_unsafe_innerhtml"


def test_pr_summary_caps_repeated_repo_wide_noise_when_files_unchanged() -> None:
    changed_scope = _finding("pr_code_change_without_test_delta", "public/app.js", severity="medium")
    dependencies = [
        _finding("dependency_risk_policy_violation", f"package.json:{line}", severity="medium")
        for line in (10, 11, 12)
    ]
    generated_test_quality = [
        _finding("agent_generated_test_nondeterministic_dependency", f"tests/generated.test.ts:{line}", severity="medium")
        for line in (20, 21, 22)
    ]

    summary = build_pr_summary(
        _result([changed_scope, *dependencies, *generated_test_quality]),
        [],
        changed_files={"public/app.js"},
    )

    top_dependency_count = sum(1 for finding in summary.top_findings if finding.rule_id == "dependency_risk_policy_violation")
    top_test_quality_count = sum(
        1 for finding in summary.top_findings if finding.rule_id == "agent_generated_test_nondeterministic_dependency"
    )
    action_dependency_count = sum(1 for action in summary.top_actions if action.rule_id == "dependency_risk_policy_violation")
    hint_dependency_count = sum(1 for hint in summary.suppression_hints if hint.startswith("dependency_risk_policy_violation"))

    assert top_dependency_count == 1
    assert top_test_quality_count == 1
    assert action_dependency_count == 1
    assert hint_dependency_count == 1


def test_pr_summary_keeps_repeated_findings_when_source_changed() -> None:
    dependencies = [
        _finding("dependency_risk_policy_violation", f"package.json:{line}", severity="medium")
        for line in (10, 11, 12)
    ]

    summary = build_pr_summary(
        _result(dependencies),
        [],
        changed_files={"package.json"},
    )

    top_dependency_count = sum(1 for finding in summary.top_findings if finding.rule_id == "dependency_risk_policy_violation")

    assert top_dependency_count == 3
