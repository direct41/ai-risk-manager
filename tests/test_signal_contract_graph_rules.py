from __future__ import annotations

from ai_risk_manager.collectors.plugins.base import ArtifactBundle
from ai_risk_manager.graph.builder import build_graph
from ai_risk_manager.rules.engine import run_rules
from ai_risk_manager.schemas.types import to_dict
from ai_risk_manager.signals.adapters import artifact_bundle_to_signal_bundle
from ai_risk_manager.signals.types import CapabilitySignal, SignalBundle


def _fixture_artifacts() -> ArtifactBundle:
    return ArtifactBundle(
        write_endpoints=[
            ("app/api.py", "create_order", "post", "/orders", 10, "@router.post('/orders')"),
        ],
        endpoint_models=[
            ("app/api.py", "create_order", "CreateOrderRequest"),
        ],
        pydantic_models=[
            ("app/schemas.py", "CreateOrderRequest"),
        ],
        declared_transitions=[
            ("app/domain.py", "OrderStatus", "pending", "paid", 22, "ALLOWED_TRANSITIONS = {...}"),
        ],
        handled_transitions=[
            ("app/service.py", "pay_order", "pending", "paid", 45, "order.status = 'paid'", False),
        ],
        test_cases=[
            ("tests/test_order.py", "test_create_order", 6, "def test_create_order(client): ..."),
        ],
        test_http_calls=[
            ("tests/test_order.py", "test_create_order", "post", "/orders", 8, "client.post('/orders')"),
        ],
        dependency_specs=[
            ("requirements.txt", "requests", ">=2.31.0", 1, "range_not_pinned", "runtime"),
        ],
    )


def test_graph_builder_accepts_signal_bundle_with_equivalent_output() -> None:
    artifacts = _fixture_artifacts()
    signals = artifact_bundle_to_signal_bundle(artifacts)

    graph_from_artifacts = build_graph(artifacts)
    graph_from_signals = build_graph(signals)

    assert to_dict(graph_from_artifacts) == to_dict(graph_from_signals)


def test_rule_engine_accepts_signal_bundle_with_equivalent_output() -> None:
    artifacts = _fixture_artifacts()
    signals = artifact_bundle_to_signal_bundle(artifacts)

    findings_from_graph = run_rules(build_graph(artifacts), risk_policy="balanced")
    findings_from_signals = run_rules(signals, risk_policy="balanced")

    assert to_dict(findings_from_graph) == to_dict(findings_from_signals)


def test_graph_builder_parses_windows_source_ref_without_truncation() -> None:
    signals = SignalBundle(
        signals=[
            CapabilitySignal(
                id="sig-win",
                kind="http_write_surface",
                source_ref=r"C:\repo\app\api.py:10",
                confidence="high",
                evidence_refs=[r"C:\repo\app\api.py:10"],
                attributes={
                    "endpoint_name": "create_order",
                    "method": "POST",
                    "path": "/orders",
                    "snippet": "@router.post('/orders')",
                },
            ),
            CapabilitySignal(
                id="sig-win-test",
                kind="test_to_endpoint_coverage",
                source_ref=r"C:\repo\tests\test_api.py:6",
                confidence="high",
                evidence_refs=[r"C:\repo\tests\test_api.py:6"],
                attributes={
                    "test_name": "test_create_order",
                    "method": "POST",
                    "path": "/orders",
                    "snippet": "client.post('/orders')",
                },
            ),
        ],
        supported_kinds={"http_write_surface", "test_to_endpoint_coverage"},
    )

    graph = build_graph(signals)
    api_node = next(node for node in graph.nodes if node.type == "API")

    assert api_node.source_ref == r"C:\repo\app\api.py:10"
