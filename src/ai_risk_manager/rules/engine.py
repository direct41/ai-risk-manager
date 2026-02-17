from __future__ import annotations

from ai_risk_manager.schemas.types import Finding, FindingsReport, Graph


def run_rules(graph: Graph) -> FindingsReport:
    findings: list[Finding] = []
    api_nodes = [n for n in graph.nodes if n.type == "API"]
    covered_api_ids = {e.target_node_id for e in graph.edges if e.type == "covered_by"}

    for api in api_nodes:
        if api.id not in covered_api_ids:
            finding_id = f"critical_path_no_tests:{api.id}"
            findings.append(
                Finding(
                    id=finding_id,
                    rule_id="critical_path_no_tests",
                    title=f"Write endpoint '{api.name}' has no matching tests",
                    description="Critical path endpoint appears uncovered by tests in current graph.",
                    severity="high",
                    confidence="medium",
                    evidence=f"No covered_by edge found for {api.id}",
                    source_ref=api.source_ref,
                    suppression_key=f"{finding_id}",
                    recommendation=f"Add API/service tests for endpoint '{api.name}', including success and error paths.",
                )
            )

    return FindingsReport(findings=findings, generated_without_llm=True)
