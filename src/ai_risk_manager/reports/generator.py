from __future__ import annotations

from collections import Counter
from pathlib import Path

from ai_risk_manager.schemas.types import FindingsReport, PipelineResult, TestPlan


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
    for note in notes:
        lines.append(f"- Provider note: {note}")

    lines.append("")
    lines.append("## Top Risks")
    lines.append("")
    if not result.findings.findings:
        lines.append("No risks detected in current scope.")
    else:
        top = sorted(
            result.findings.findings,
            key=lambda f: ("critical high medium low".split().index(f.severity), f.rule_id),
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
