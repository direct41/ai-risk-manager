from __future__ import annotations

from unittest.mock import patch

from ai_risk_manager.agents.llm_runtime import LLMRuntimeError
from ai_risk_manager.agents.qa_strategy_agent import generate_test_plan
from ai_risk_manager.agents.risk_agent import generate_findings
from ai_risk_manager.agents.semantic_risk_agent import generate_semantic_findings
from ai_risk_manager.schemas.types import Edge, Finding, FindingsReport, Graph, Node


def _sample_graph() -> Graph:
    return Graph(
        nodes=[
            Node(id="api:create_order", type="API", name="create_order", layer="infrastructure", source_ref="app/api.py"),
            Node(id="test:test_create_order", type="TestCase", name="test_create_order", layer="qa", source_ref="tests/test_api.py"),
        ],
        edges=[
            Edge(
                id="edge:test->api",
                source_node_id="test:test_create_order",
                target_node_id="api:create_order",
                type="covered_by",
                source_ref="tests/test_api.py",
                evidence="name overlap",
            )
        ],
    )


def _sample_findings_raw() -> FindingsReport:
    return FindingsReport(
        findings=[
            Finding(
                id="critical_path_no_tests:api:create_order",
                rule_id="critical_path_no_tests",
                title="Write endpoint has no matching tests",
                description="desc",
                severity="high",
                confidence="medium",
                evidence="e",
                source_ref="app/api.py",
                suppression_key="k",
                recommendation="add tests",
            )
        ],
        generated_without_llm=True,
    )


def test_risk_agent_uses_llm_payload_when_valid() -> None:
    findings_raw = _sample_findings_raw()
    graph = _sample_graph()

    llm_payload = {
        "findings": [
            {
                "id": "x1",
                "rule_id": "critical_path_no_tests",
                "title": "t",
                "description": "d",
                "severity": "high",
                "confidence": "high",
                "evidence": "ev",
                "source_ref": "app/api.py",
                "suppression_key": "sk",
                "recommendation": "do",
                "generated_without_llm": False,
            }
        ]
    }

    with patch("ai_risk_manager.agents.risk_agent.call_llm_json", return_value=llm_payload):
        report = generate_findings(findings_raw, graph, provider="api", generated_without_llm=False)

    assert report.generated_without_llm is False
    assert report.findings[0].id == "x1"


def test_risk_agent_degrades_to_deterministic_on_llm_failure() -> None:
    findings_raw = _sample_findings_raw()
    graph = _sample_graph()

    with patch("ai_risk_manager.agents.risk_agent.call_llm_json", side_effect=LLMRuntimeError("boom")):
        report = generate_findings(findings_raw, graph, provider="api", generated_without_llm=False)

    assert report.generated_without_llm is True
    assert all(f.confidence == "low" for f in report.findings)


def test_qa_agent_degrades_to_deterministic_on_llm_failure() -> None:
    findings = _sample_findings_raw()
    graph = _sample_graph()

    with patch("ai_risk_manager.agents.qa_strategy_agent.call_llm_json", side_effect=LLMRuntimeError("boom")):
        plan = generate_test_plan(findings, graph, provider="api", generated_without_llm=False)

    assert plan.generated_without_llm is True
    assert len(plan.items) == 1
    assert all(item.confidence == "low" for item in plan.items)


def test_qa_agent_uses_valid_ai_payload() -> None:
    findings = _sample_findings_raw()
    graph = _sample_graph()
    payload = {
        "items": [
            {
                "id": "t1",
                "title": "Add endpoint test",
                "priority": "high",
                "finding_id": findings.findings[0].id,
                "source_ref": "tests/test_api.py:4",
                "recommendation": "Add error path test",
                "test_type": "api",
                "test_target": "POST /orders",
                "assertions": ["status code", "validation error payload"],
                "confidence": "high",
                "generated_without_llm": False,
            }
        ]
    }

    with patch("ai_risk_manager.agents.qa_strategy_agent.call_llm_json", return_value=payload):
        plan = generate_test_plan(findings, graph, provider="api", generated_without_llm=False)

    assert plan.generated_without_llm is False
    assert plan.items[0].test_type == "api"
    assert plan.items[0].assertions


def test_semantic_agent_degrades_on_invalid_payload() -> None:
    graph = _sample_graph()
    payload = {
        "findings": [
            {
                "id": "s1",
                "rule_id": "semantic_gap",
                "title": "missing evidence refs",
                "description": "d",
                "severity": "high",
                "confidence": "medium",
                "evidence": "e",
                "source_ref": "app/api.py:1",
                "recommendation": "r",
            }
        ]
    }

    with patch("ai_risk_manager.agents.semantic_risk_agent.call_llm_json", return_value=payload):
        report, notes = generate_semantic_findings(graph, provider="api", generated_without_llm=False)

    assert report.generated_without_llm is True
    assert not report.findings
    assert any("degraded" in note for note in notes)


def test_semantic_agent_uses_valid_payload() -> None:
    graph = _sample_graph()
    payload = {
        "findings": [
            {
                "id": "s2",
                "rule_id": "semantic_risk",
                "title": "State validation gap",
                "description": "d",
                "severity": "high",
                "confidence": "high",
                "evidence": "endpoint accepts invalid transition",
                "source_ref": "app/api.py:10",
                "suppression_key": "semantic_risk:s2",
                "recommendation": "add invariant checks",
                "evidence_refs": ["app/api.py:10"],
            }
        ]
    }

    with patch("ai_risk_manager.agents.semantic_risk_agent.call_llm_json", return_value=payload):
        report, _ = generate_semantic_findings(graph, provider="api", generated_without_llm=False)

    assert report.generated_without_llm is False
    assert len(report.findings) == 1
    assert report.findings[0].origin == "ai"


def test_semantic_agent_degrades_on_unknown_severity() -> None:
    graph = _sample_graph()
    payload = {
        "findings": [
            {
                "id": "s3",
                "rule_id": "semantic_risk",
                "title": "Unexpected severity label",
                "description": "d",
                "severity": "info",
                "confidence": "high",
                "evidence": "e",
                "source_ref": "app/api.py:1",
                "recommendation": "r",
                "evidence_refs": ["app/api.py:1"],
            }
        ]
    }

    with patch("ai_risk_manager.agents.semantic_risk_agent.call_llm_json", return_value=payload):
        report, notes = generate_semantic_findings(graph, provider="api", generated_without_llm=False)

    assert report.generated_without_llm is True
    assert not report.findings
    assert any("Unsupported semantic finding severity" in note for note in notes)
