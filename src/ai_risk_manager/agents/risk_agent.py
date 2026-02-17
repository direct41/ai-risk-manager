from __future__ import annotations

from dataclasses import replace
import json

from ai_risk_manager.agents.llm_runtime import LLMRuntimeError, call_llm_json
from ai_risk_manager.schemas.types import Finding, FindingsReport, Graph


def _deterministic_findings(findings_raw: FindingsReport, *, generated_without_llm: bool) -> FindingsReport:
    enriched = [replace(finding, generated_without_llm=generated_without_llm) for finding in findings_raw.findings]
    return FindingsReport(findings=enriched, generated_without_llm=generated_without_llm)


def _validate_findings_payload(payload: dict) -> FindingsReport:
    rows = payload.get("findings")
    if not isinstance(rows, list):
        raise ValueError("LLM findings payload must contain list field 'findings'")

    findings: list[Finding] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each finding row must be an object")
        findings.append(Finding(**row))
    return FindingsReport(findings=findings, generated_without_llm=False)


def generate_findings(
    findings_raw: FindingsReport,
    graph: Graph,
    *,
    provider: str,
    generated_without_llm: bool,
) -> FindingsReport:
    if generated_without_llm or provider == "none":
        return _deterministic_findings(findings_raw, generated_without_llm=True)

    prompt_payload = {
        "task": "Rewrite raw findings into final findings JSON without adding fields.",
        "rules": ["Return only JSON object with key 'findings'."],
        "raw_findings": [finding.__dict__ for finding in findings_raw.findings],
        "graph_context": {
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
        },
    }
    prompt = json.dumps(prompt_payload, ensure_ascii=False)

    try:
        payload = call_llm_json(provider, prompt, max_retries=2)
        return _validate_findings_payload(payload)
    except (LLMRuntimeError, ValueError, TypeError):
        degraded = _deterministic_findings(findings_raw, generated_without_llm=True)
        degraded.findings = [replace(finding, confidence="low") for finding in degraded.findings]
        return degraded
