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


def test_artifact_bundle_to_signal_bundle_maps_side_effect_contract() -> None:
    artifacts = ArtifactBundle(
        side_effect_requirements=[
            ("app/service.py", "create_order", "event", "order.created", 21, "require emit order.created"),
        ],
        side_effect_emits=[
            ("app/service.py", "emit_order_created", "event", "order.created", 34, "emit('order.created')"),
        ],
    )

    bundle = artifact_bundle_to_signal_bundle(artifacts)
    side_effect_signals = [signal for signal in bundle.signals if signal.kind == "side_effect_emit_contract"]

    assert len(side_effect_signals) == 2
    roles = {str(signal.attributes.get("role")) for signal in side_effect_signals}
    assert roles == {"required", "emitted"}
    assert "side_effect_emit_contract" in bundle.supported_kinds


def test_artifact_bundle_to_signal_bundle_maps_authorization_contract() -> None:
    artifacts = ArtifactBundle(
        authorization_boundaries=[
            (
                "app/api.py",
                "create_order",
                "decorator",
                "order.write",
                12,
                "@requires_permission('order.write')",
            )
        ]
    )

    bundle = artifact_bundle_to_signal_bundle(artifacts)
    authz_signals = [signal for signal in bundle.signals if signal.kind == "authorization_boundary_enforced"]

    assert len(authz_signals) == 1
    authz = authz_signals[0]
    assert authz.attributes["owner_name"] == "create_order"
    assert authz.attributes["auth_mechanism"] == "decorator"
    assert authz.attributes["auth_subject"] == "order.write"
    assert "authorization_boundary_enforced" in bundle.supported_kinds


def test_artifact_bundle_to_signal_bundle_maps_integrity_and_frontend_safety_contracts() -> None:
    artifacts = ArtifactBundle(
        write_contract_issues=[
            (
                "server/services/notesService.js",
                "db_insert_binding_mismatch",
                "createNote",
                42,
                "INSERT INTO notes (...) VALUES (...)",
                {"column": "title", "value_field": "content"},
            )
        ],
        session_lifecycle_issues=[
            (
                "public/app.js",
                "storage_key_mismatch",
                "localStorage",
                81,
                "localStorage.removeItem('session_token')",
                {"set_key": "sessionToken", "remove_key": "session_token"},
            )
        ],
        html_render_issues=[
            (
                "public/app.js",
                "unsanitized_innerhtml",
                "renderNotes",
                120,
                "refs.notesContainer.innerHTML = ...",
                {"sink": "refs.notesContainer.innerHTML"},
            )
        ],
        ui_ergonomics_issues=[
            (
                "public/app.js",
                "pagination_page_not_normalized_after_mutation",
                "loadNotes",
                114,
                "async function loadNotes()",
                {"state_field": "state.page"},
            )
        ],
    )

    bundle = artifact_bundle_to_signal_bundle(artifacts)
    kinds = {signal.kind for signal in bundle.signals}

    assert "write_contract_integrity" in kinds
    assert "session_lifecycle_consistency" in kinds
    assert "html_render_safety" in kinds
    assert "ui_ergonomics" in kinds
    assert "write_contract_integrity" in bundle.supported_kinds
    assert "session_lifecycle_consistency" in bundle.supported_kinds
    assert "html_render_safety" in bundle.supported_kinds
    assert "ui_ergonomics" in bundle.supported_kinds
