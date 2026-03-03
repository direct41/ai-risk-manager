from __future__ import annotations

from ai_risk_manager.rules.engine import run_rules
from ai_risk_manager.signals.types import CapabilitySignal, SignalBundle


def test_missing_required_side_effect_is_reported_when_emit_is_absent() -> None:
    signals = SignalBundle(
        signals=[
            CapabilitySignal(
                id="sig:req:create_order",
                kind="side_effect_emit_contract",
                source_ref="app/service.py:20",
                confidence="medium",
                evidence_refs=["app/service.py:20"],
                attributes={
                    "role": "required",
                    "owner_name": "create_order",
                    "effect_kind": "event",
                    "effect_target": "order.created",
                },
            )
        ],
        supported_kinds={"side_effect_emit_contract"},
    )

    findings = run_rules(signals, risk_policy="balanced")

    assert any(row.rule_id == "missing_required_side_effect" for row in findings.findings)


def test_missing_required_side_effect_is_not_reported_when_emit_exists() -> None:
    signals = SignalBundle(
        signals=[
            CapabilitySignal(
                id="sig:req:create_order",
                kind="side_effect_emit_contract",
                source_ref="app/service.py:20",
                confidence="medium",
                evidence_refs=["app/service.py:20"],
                attributes={
                    "role": "required",
                    "owner_name": "create_order",
                    "effect_kind": "event",
                    "effect_target": "order.created",
                },
            ),
            CapabilitySignal(
                id="sig:emit:create_order",
                kind="side_effect_emit_contract",
                source_ref="app/service.py:34",
                confidence="medium",
                evidence_refs=["app/service.py:34"],
                attributes={
                    "role": "emitted",
                    "owner_name": "create_order",
                    "effect_kind": "event",
                    "effect_target": "order.created",
                },
            ),
        ],
        supported_kinds={"side_effect_emit_contract"},
    )

    findings = run_rules(signals, risk_policy="balanced")

    assert all(row.rule_id != "missing_required_side_effect" for row in findings.findings)


def test_critical_write_missing_authz_is_reported_when_supported_but_not_present() -> None:
    signals = SignalBundle(
        signals=[
            CapabilitySignal(
                id="sig:http:create_order",
                kind="http_write_surface",
                source_ref="app/api.py:12",
                confidence="high",
                evidence_refs=["app/api.py:12"],
                attributes={
                    "endpoint_name": "create_order",
                    "method": "POST",
                    "path": "/orders",
                },
            )
        ],
        supported_kinds={"http_write_surface", "authorization_boundary_enforced"},
    )

    findings = run_rules(signals, risk_policy="balanced")

    assert any(row.rule_id == "critical_write_missing_authz" for row in findings.findings)


def test_critical_write_missing_authz_is_not_reported_when_boundary_exists() -> None:
    signals = SignalBundle(
        signals=[
            CapabilitySignal(
                id="sig:http:create_order",
                kind="http_write_surface",
                source_ref="app/api.py:12",
                confidence="high",
                evidence_refs=["app/api.py:12"],
                attributes={
                    "endpoint_name": "create_order",
                    "method": "POST",
                    "path": "/orders",
                },
            ),
            CapabilitySignal(
                id="sig:authz:create_order",
                kind="authorization_boundary_enforced",
                source_ref="app/api.py:8",
                confidence="medium",
                evidence_refs=["app/api.py:8"],
                attributes={
                    "owner_name": "create_order",
                    "auth_mechanism": "decorator",
                    "auth_subject": "order.write",
                },
            ),
        ],
        supported_kinds={"http_write_surface", "authorization_boundary_enforced"},
    )

    findings = run_rules(signals, risk_policy="balanced")

    assert all(row.rule_id != "critical_write_missing_authz" for row in findings.findings)


def test_critical_write_missing_authz_is_not_reported_when_capability_is_not_supported() -> None:
    signals = SignalBundle(
        signals=[
            CapabilitySignal(
                id="sig:http:create_order",
                kind="http_write_surface",
                source_ref="app/api.py:12",
                confidence="high",
                evidence_refs=["app/api.py:12"],
                attributes={
                    "endpoint_name": "create_order",
                    "method": "POST",
                    "path": "/orders",
                },
            )
        ],
        supported_kinds={"http_write_surface"},
    )

    findings = run_rules(signals, risk_policy="balanced")

    assert all(row.rule_id != "critical_write_missing_authz" for row in findings.findings)
