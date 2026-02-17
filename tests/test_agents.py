from __future__ import annotations

from unittest.mock import patch

from ai_risk_manager.agents.qa_strategy_agent import generate_test_plan
from ai_risk_manager.agents.risk_agent import generate_findings
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

    with patch("ai_risk_manager.agents.risk_agent.call_llm_json", side_effect=RuntimeError("boom")):
        report = generate_findings(findings_raw, graph, provider="api", generated_without_llm=False)

    assert report.generated_without_llm is True
    assert all(f.confidence == "low" for f in report.findings)


def test_qa_agent_degrades_to_deterministic_on_llm_failure() -> None:
    findings = _sample_findings_raw()
    graph = _sample_graph()

    with patch("ai_risk_manager.agents.qa_strategy_agent.call_llm_json", side_effect=RuntimeError("boom")):
        plan = generate_test_plan(findings, graph, provider="api", generated_without_llm=False)

    assert plan.generated_without_llm is True
    assert len(plan.items) == 1
