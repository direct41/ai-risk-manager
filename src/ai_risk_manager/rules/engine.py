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
                    origin="deterministic",
                    evidence_refs=[api.source_ref],
                )
            )

    declared_pairs = {(t.source, t.target) for t in graph.declared_transitions}
    handled_pairs = {(t.source, t.target) for t in graph.handled_transitions}
    missing_pairs = declared_pairs - handled_pairs
    for source, target in sorted(missing_pairs):
        source_ref = next((t.source_ref for t in graph.declared_transitions if t.source == source and t.target == target), "unknown")
        finding_id = f"missing_transition_handler:{source}->{target}"
        findings.append(
            Finding(
                id=finding_id,
                rule_id="missing_transition_handler",
                title=f"Declared transition '{source} -> {target}' has no handler",
                description="A declared transition exists but no matching status-change handler was found.",
                severity="medium",
                confidence="medium",
                evidence=f"Declared transitions include {source}->{target}; handled transitions do not.",
                source_ref=source_ref,
                suppression_key=finding_id,
                recommendation=f"Implement handler logic for transition '{source} -> {target}' or remove stale declaration.",
                origin="deterministic",
                evidence_refs=[source_ref],
            )
        )

    for transition in graph.handled_transitions:
        if transition.invariant_guarded:
            continue
        finding_id = f"broken_invariant_on_transition:{transition.machine}:{transition.source}->{transition.target}"
        findings.append(
            Finding(
                id=finding_id,
                rule_id="broken_invariant_on_transition",
                title=f"Transition '{transition.source} -> {transition.target}' lacks invariant guard",
                description=(
                    "State transition handler mutates status without explicit invariant/guard validation before write."
                ),
                severity="high",
                confidence="medium",
                evidence=(
                    f"Detected direct transition '{transition.source}->{transition.target}' in handler "
                    f"'{transition.machine}' without guard markers."
                ),
                source_ref=transition.source_ref,
                suppression_key=finding_id,
                recommendation=(
                    f"Add explicit guard checks for transition '{transition.source} -> {transition.target}' "
                    f"in handler '{transition.machine}' (assertions/validation/policy checks)."
                ),
                origin="deterministic",
                evidence_refs=[transition.source_ref],
            )
        )

    return FindingsReport(findings=findings, generated_without_llm=True)
