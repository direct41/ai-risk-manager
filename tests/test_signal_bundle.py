from __future__ import annotations

from ai_risk_manager.collectors.plugins.base import ArtifactBundle
from ai_risk_manager.signals.adapters import artifact_bundle_to_signal_bundle


def test_artifact_bundle_to_signal_bundle_maps_core_capabilities() -> None:
    artifacts = ArtifactBundle(
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

    bundle = artifact_bundle_to_signal_bundle(artifacts)
    kinds = {signal.kind for signal in bundle.signals}

    assert "http_write_surface" in kinds
    assert "request_contract_binding" in kinds
    assert "state_transition_declared" in kinds
    assert "state_transition_handled_guarded" in kinds
    assert "test_to_endpoint_coverage" in kinds
    assert "dependency_version_policy" in kinds
    assert "side_effect_emit_contract" not in kinds
    assert "authorization_boundary_enforced" not in kinds
    assert bundle.supported_kinds == {
        "http_write_surface",
        "request_contract_binding",
        "state_transition_declared",
        "state_transition_handled_guarded",
        "test_to_endpoint_coverage",
        "dependency_version_policy",
    }


def test_artifact_bundle_to_signal_bundle_populates_evidence_refs() -> None:
    artifacts = ArtifactBundle(
        write_endpoints=[("app/api.py", "create_order", "post", "/orders", 10, "snippet")],
    )

    bundle = artifact_bundle_to_signal_bundle(artifacts)

    assert bundle.signals
    assert all(signal.evidence_refs for signal in bundle.signals)
