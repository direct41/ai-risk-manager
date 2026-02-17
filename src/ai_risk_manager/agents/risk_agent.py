from __future__ import annotations

from ai_risk_manager.schemas.types import Finding, FindingsReport, Graph


def generate_findings(
    findings_raw: FindingsReport,
    graph: Graph,
    *,
    provider: str,
    generated_without_llm: bool,
) -> FindingsReport:
    # MVP: deterministic enrichment. Graph/provider are kept to preserve stable interface.
    _ = graph
    enriched: list[Finding] = []
    for finding in findings_raw.findings:
        enriched.append(
            Finding(
                **{**finding.__dict__, "generated_without_llm": generated_without_llm},
            )
        )

    return FindingsReport(findings=enriched, generated_without_llm=generated_without_llm)
