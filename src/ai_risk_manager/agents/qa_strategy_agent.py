from __future__ import annotations

from dataclasses import replace
import json
import os

from ai_risk_manager.agents.llm_runtime import LLMRuntimeError, call_llm_json
from ai_risk_manager.schemas.types import FindingsReport, Graph, TestPlan, TestRecommendation, to_dict


def _qa_llm_timeout_seconds() -> float:
    raw = os.getenv("AIRISK_QA_LLM_TIMEOUT_SECONDS", "20")
    try:
        value = float(raw)
    except ValueError:
        return 20.0
    return value if value > 0 else 20.0


def _qa_llm_max_retries() -> int:
    raw = os.getenv("AIRISK_QA_LLM_MAX_RETRIES", "0")
    try:
        value = int(raw)
    except ValueError:
        return 0
    return value if value >= 0 else 0


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
                test_type="api",
                test_target=finding.source_ref,
                assertions=[
                    "Validate success response path.",
                    "Validate failure/validation response path.",
                ],
                confidence="medium",
                generated_without_llm=generated_without_llm,
            )
        )
    return TestPlan(items=items, generated_without_llm=generated_without_llm)


def _low_confidence_plan(plan: TestPlan) -> TestPlan:
    return TestPlan(
        items=[replace(item, confidence="low", generated_without_llm=True) for item in plan.items],
        generated_without_llm=True,
    )


def _validate_test_plan_payload(payload: dict) -> TestPlan:
    rows = payload.get("items")
    if not isinstance(rows, list):
        raise ValueError("LLM test-plan payload must contain list field 'items'")

    items: list[TestRecommendation] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each test-plan row must be an object")
        required = ("test_type", "test_target", "assertions")
        if not all(key in row for key in required):
            raise ValueError("Each AI test-plan row must include test_type, test_target, assertions")
        assertions = row.get("assertions")
        if not isinstance(assertions, list) or not all(isinstance(assertion, str) for assertion in assertions):
            raise ValueError("Test-plan assertions must be a list of strings")
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

    qa_nodes = [to_dict(node) for node in graph.nodes if node.type == "TestCase"]
    covered_edges = [to_dict(edge) for edge in graph.edges if edge.type == "covered_by"]
    prompt_payload = {
        "task": "Create prioritized test recommendations as JSON.",
        "rules": ["Return only JSON object with key 'items'."],
        "findings": [to_dict(finding) for finding in findings.findings],
        "qa_context": {
            "test_nodes": qa_nodes,
            "covered_edges": covered_edges,
        },
    }
    prompt = json.dumps(prompt_payload, ensure_ascii=False)

    try:
        payload = call_llm_json(
            provider,
            prompt,
            max_retries=_qa_llm_max_retries(),
            timeout_seconds=_qa_llm_timeout_seconds(),
        )
        return _validate_test_plan_payload(payload)
    except (LLMRuntimeError, ValueError, TypeError):
        return _low_confidence_plan(_deterministic_test_plan(findings, generated_without_llm=True))
