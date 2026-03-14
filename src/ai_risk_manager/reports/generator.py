from __future__ import annotations

from collections import Counter
from pathlib import Path

from ai_risk_manager.schemas.types import FindingsReport, PipelineResult

SEVERITY_ORDER = "critical high medium low".split()
CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}
SEVERITY_INDEX = {severity: idx for idx, severity in enumerate(SEVERITY_ORDER)}


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

    return "\n".join(lines).strip() + "\n"


def write_report(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def render_pr_summary_md(result: PipelineResult, notes: list[str], *, only_new: bool = False) -> str:
    marker = "<!-- ai-risk-manager -->"
    lines = [marker, "## AI Risk Manager Summary", ""]
    lines.append(f"- analysis_scope: `{result.analysis_scope}`")
    lines.append(f"- support_level_applied: `{result.summary.support_level_applied}`")
    lines.append(f"- repository_support_state: `{result.summary.repository_support_state}`")
    lines.append(f"- effective_ci_mode: `{result.summary.effective_ci_mode}`")
    lines.append(f"- competitive_mode: `{result.summary.competitive_mode}`")
    lines.append(f"- graph_mode_applied: `{result.summary.graph_mode_applied}`")
    lines.append(f"- semantic_signal_count: `{result.summary.semantic_signal_count}`")
    lines.append(f"- findings: `{len(result.findings.findings)}`")
    lines.append(
        f"- new/resolved/unchanged: `{result.summary.new_count}/{result.summary.resolved_count}/{result.summary.unchanged_count}`"
    )
    if result.summary.fallback_reason:
        lines.append(f"- fallback_reason: `{result.summary.fallback_reason}`")
    if notes:
        lines.append(f"- notes: `{'; '.join(notes)}`")
    lines.append("")

    top_candidates = result.findings.findings
    if only_new:
        min_rank = SEVERITY_INDEX["high"]
        top_candidates = [
            finding
            for finding in top_candidates
            if finding.status == "new" and SEVERITY_INDEX.get(finding.severity, len(SEVERITY_ORDER)) <= min_rank
        ]

    top = _rank_findings(top_candidates)[:5]
    if not top:
        lines.append("No findings in current PR scope.")
    else:
        lines.append("### Top Findings")
        lines.append("")
        for finding in top:
            lines.append(
                f"- [{finding.severity}] [{finding.status}] `{finding.rule_id}` at `{finding.source_ref}`: "
                f"{finding.title}. confidence=`{finding.confidence}`, evidence_refs=`{len(finding.evidence_refs)}`. "
                f"Action: {finding.recommendation}"
            )
    lines.append("")
    lines.append("Full details: see workflow artifacts (`report.md`, `findings.json`, `test_plan.json`).")
    return "\n".join(lines).strip() + "\n"
