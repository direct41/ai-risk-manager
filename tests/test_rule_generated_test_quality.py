from __future__ import annotations

from ai_risk_manager.rules.engine import run_rules
from ai_risk_manager.signals.types import CapabilitySignal, SignalBundle


def test_generated_test_quality_reports_missing_negative_path() -> None:
    findings = run_rules(
        SignalBundle(
            signals=[
                CapabilitySignal(
                    id="sig-generated-negative-gap",
                    kind="generated_test_quality",
                    source_ref="tests/test_orders.py:4",
                    confidence="medium",
                    evidence_refs=["tests/test_orders.py:4"],
                    attributes={
                        "issue_type": "missing_negative_path",
                        "test_name": "test_create_order",
                        "method": "POST",
                        "path": "/orders",
                    },
                )
            ],
            supported_kinds={"generated_test_quality"},
        )
    )
    assert any(row.rule_id == "agent_generated_test_missing_negative_path" for row in findings.findings)


def test_generated_test_quality_reports_nondeterministic_dependency() -> None:
    findings = run_rules(
        SignalBundle(
            signals=[
                CapabilitySignal(
                    id="sig-generated-flaky",
                    kind="generated_test_quality",
                    source_ref="tests/test_orders.py:11",
                    confidence="medium",
                    evidence_refs=["tests/test_orders.py:11"],
                    attributes={
                        "issue_type": "nondeterministic_dependency",
                        "test_name": "test_create_order_eventually",
                        "dependency_kinds": "sleep,time",
                    },
                )
            ],
            supported_kinds={"generated_test_quality"},
        )
    )
    assert any(row.rule_id == "agent_generated_test_nondeterministic_dependency" for row in findings.findings)
