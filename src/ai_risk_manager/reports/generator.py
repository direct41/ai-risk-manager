from __future__ import annotations

from collections import Counter
from pathlib import Path

from ai_risk_manager.schemas.types import FindingsReport, PipelineResult, TestPlan

SEVERITY_ORDER = "critical high medium low".split()


def _summary_counts(findings: FindingsReport) -> dict[str, int]:
    counts = Counter(f.severity for f in findings.findings)
    return {
        "critical": counts.get("critical", 0),
        "high": counts.get("high", 0),
        "medium": counts.get("medium", 0),
        "low": counts.get("low", 0),
    }


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
    lines.append(f"- Data Quality (low-confidence ratio): `{result.data_quality_low_confidence_ratio:.2%}`")
    lines.append(f"- Graph Statistics: `{len(result.graph.nodes)} nodes`, `{len(result.graph.edges)} edges`")
    lines.append(f"- Suppressed findings: `{result.suppressed_count}`")
    for note in notes:
        lines.append(f"- Provider note: {note}")

    lines.append("")
    lines.append("## Why This Matters for Release Risk")
    lines.append("")
    if not result.findings.findings:
        lines.append("No high-signal release risks detected in current scope.")
    else:
        top_severity = sorted(result.findings.findings, key=lambda f: SEVERITY_ORDER.index(f.severity))[0].severity
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
        actions = sorted(result.findings.findings, key=lambda f: SEVERITY_ORDER.index(f.severity))[:5]
        for finding in actions:
            lines.append(f"- Action: {finding.recommendation}")
            lines.append(f"  Expected impact: reduce `{finding.rule_id}` risk around `{finding.source_ref}`.")

    lines.append("")
    lines.append("## Top Risks")
    lines.append("")
    if not result.findings.findings:
        lines.append("No risks detected in current scope.")
    else:
        top = sorted(
            result.findings.findings,
            key=lambda f: (SEVERITY_ORDER.index(f.severity), f.rule_id),
        )[:5]
        for finding in top:
            lines.append(f"### {finding.title}")
            lines.append(f"- Severity: `{finding.severity}`")
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
        lines.append(f"- [{finding.severity}] `{finding.rule_id}` at `{finding.source_ref}`: {finding.title}")

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


def render_pr_summary_md(result: PipelineResult, notes: list[str]) -> str:
    marker = "<!-- ai-risk-manager -->"
    lines = [marker, "## AI Risk Manager Summary", ""]
    lines.append(f"- analysis_scope: `{result.analysis_scope}`")
    lines.append(f"- findings: `{len(result.findings.findings)}`")
    if notes:
        lines.append(f"- notes: `{'; '.join(notes)}`")
    lines.append("")

    top = sorted(
        result.findings.findings,
        key=lambda f: (SEVERITY_ORDER.index(f.severity), f.rule_id),
    )[:5]
    if not top:
        lines.append("No findings in current PR scope.")
    else:
        lines.append("### Top Findings")
        lines.append("")
        for finding in top:
            lines.append(
                f"- [{finding.severity}] `{finding.rule_id}` at `{finding.source_ref}`: "
                f"{finding.title}. Action: {finding.recommendation}"
            )
    lines.append("")
    lines.append("Full details: see workflow artifacts (`report.md`, `findings.json`, `test_plan.json`).")
    return "\n".join(lines).strip() + "\n"
