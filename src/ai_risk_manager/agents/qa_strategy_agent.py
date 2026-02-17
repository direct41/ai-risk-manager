from __future__ import annotations

import json

from ai_risk_manager.agents.llm_runtime import LLMRuntimeError, call_llm_json
from ai_risk_manager.schemas.types import FindingsReport, Graph, TestPlan, TestRecommendation


def _deterministic_test_plan(findings: FindingsReport, *, generated_without_llm: bool) -> TestPlan:
    items: list[TestRecommendation] = []
    for finding in findings.findings:
        items.append(
            TestRecommendation(
                id=f"test-plan:{finding.id}",
                title=f"Cover risk: {finding.rule_id}",
                priority=finding.severity,
                finding_id=finding.id,
                source_ref=finding.source_ref,
                recommendation=finding.recommendation,
                generated_without_llm=generated_without_llm,
            )
        )
    return TestPlan(items=items, generated_without_llm=generated_without_llm)


def _validate_test_plan_payload(payload: dict) -> TestPlan:
    rows = payload.get("items")
    if not isinstance(rows, list):
        raise ValueError("LLM test-plan payload must contain list field 'items'")

    items: list[TestRecommendation] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each test-plan row must be an object")
        items.append(TestRecommendation(**row))

    return TestPlan(items=items, generated_without_llm=False)


def generate_test_plan(
    findings: FindingsReport,
    graph: Graph,
    *,
    provider: str,
    generated_without_llm: bool,
) -> TestPlan:
    if generated_without_llm or provider == "none":
        return _deterministic_test_plan(findings, generated_without_llm=True)

    qa_nodes = [node.__dict__ for node in graph.nodes if node.type == "TestCase"]
    covered_edges = [edge.__dict__ for edge in graph.edges if edge.type == "covered_by"]
    prompt_payload = {
        "task": "Create prioritized test recommendations as JSON.",
        "rules": ["Return only JSON object with key 'items'."],
        "findings": [f.__dict__ for f in findings.findings],
        "qa_context": {
            "test_nodes": qa_nodes,
            "covered_edges": covered_edges,
        },
    }
    prompt = json.dumps(prompt_payload, ensure_ascii=False)

    try:
        payload = call_llm_json(provider, prompt, max_retries=2)
        return _validate_test_plan_payload(payload)
    except (LLMRuntimeError, ValueError, TypeError):
        return _deterministic_test_plan(findings, generated_without_llm=True)
