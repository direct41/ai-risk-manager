from __future__ import annotations

from unittest.mock import patch

from ai_risk_manager.agents.semantic_signal_agent import generate_semantic_signals
from ai_risk_manager.schemas.types import Edge, Graph, Node
from ai_risk_manager.signals.merge import merge_signal_bundles
from ai_risk_manager.signals.types import CapabilitySignal, SignalBundle


def _sample_graph() -> Graph:
    return Graph(
        nodes=[
            Node(
                id="api:create_order",
                type="API",
                name="create_order",
                layer="infrastructure",
                source_ref="app/api.py:10",
                details={"snippet": "@router.post('/orders')"},
            )
        ],
        edges=[
            Edge(
                id="edge:t->a",
                source_node_id="test:test_create_order",
                target_node_id="api:create_order",
                type="covered_by",
                source_ref="tests/test_api.py:5",
                evidence="test HTTP call",
            )
        ],
    )


def test_semantic_signal_agent_skips_without_llm() -> None:
    graph = _sample_graph()

    bundle, notes = generate_semantic_signals(graph, provider="none", generated_without_llm=True)

    assert not bundle.signals
    assert any("skipped" in note.lower() for note in notes)


def test_semantic_signal_agent_accepts_valid_payload() -> None:
    graph = _sample_graph()
    payload = {
        "signals": [
            {
                "id": "sig-ai-1",
                "kind": "authorization_boundary_enforced",
                "source_ref": "app/api.py:10",
                "confidence": "high",
                "evidence_refs": ["app/api.py:10"],
                "attributes": {
                    "boundary": "endpoint:POST /orders",
                    "enforcement": "Depends(get_current_user)",
                },
                "tags": ["authz", "critical-path"],
            }
        ]
    }

    with patch("ai_risk_manager.agents.semantic_signal_agent.call_llm_json", return_value=payload):
        bundle, notes = generate_semantic_signals(graph, provider="api", generated_without_llm=False)

    assert len(bundle.signals) == 1
    assert bundle.signals[0].kind == "authorization_boundary_enforced"
    assert bundle.signals[0].origin == "ai"
    assert any("produced 1 signal" in note.lower() for note in notes)


def test_semantic_signal_agent_degrades_on_invalid_kind() -> None:
    graph = _sample_graph()
    payload = {
        "signals": [
            {
                "id": "sig-ai-2",
                "kind": "unknown_kind",
                "source_ref": "app/api.py:10",
                "confidence": "high",
                "evidence_refs": ["app/api.py:10"],
                "attributes": {},
                "tags": [],
            }
        ]
    }

    with patch("ai_risk_manager.agents.semantic_signal_agent.call_llm_json", return_value=payload):
        bundle, notes = generate_semantic_signals(graph, provider="api", generated_without_llm=False)

    assert not bundle.signals
    assert any("degraded" in note.lower() for note in notes)


def test_semantic_signal_agent_degrades_on_missing_required_attributes() -> None:
    graph = _sample_graph()
    payload = {
        "signals": [
            {
                "id": "sig-ai-3",
                "kind": "http_write_surface",
                "source_ref": "app/api.py:10",
                "confidence": "high",
                "evidence_refs": ["app/api.py:10"],
                "attributes": {"method": "POST", "path": "/orders"},
                "tags": [],
            }
        ]
    }

    with patch("ai_risk_manager.agents.semantic_signal_agent.call_llm_json", return_value=payload):
        bundle, notes = generate_semantic_signals(graph, provider="api", generated_without_llm=False)

    assert not bundle.signals
    assert any("missing required attributes" in note.lower() for note in notes)


def test_merge_signal_bundles_deduplicates_and_keeps_higher_confidence() -> None:
    deterministic = SignalBundle(
        signals=[
            CapabilitySignal(
                id="s1",
                kind="http_write_surface",
                source_ref="app/api.py:10",
                confidence="medium",
                evidence_refs=["app/api.py:10"],
                attributes={"method": "POST", "path": "/orders"},
            )
        ],
        supported_kinds={"http_write_surface"},
    )
    ai_bundle = SignalBundle(
        signals=[
            CapabilitySignal(
                id="s2",
                kind="http_write_surface",
                source_ref="app/api.py:10",
                confidence="high",
                evidence_refs=["app/api.py:10", "tests/test_api.py:5"],
                attributes={"method": "POST", "path": "/orders"},
                origin="ai",
            )
        ],
        supported_kinds={"http_write_surface"},
    )

    merged = merge_signal_bundles(deterministic, ai_bundle, min_confidence="low")

    assert len(merged.signals) == 1
    assert merged.signals[0].confidence == "high"
    assert "tests/test_api.py:5" in merged.signals[0].evidence_refs
