from __future__ import annotations

from ai_risk_manager.rules.engine import run_rules
from ai_risk_manager.signals.types import CapabilitySignal, SignalBundle


def test_business_critical_flow_changed_without_check_delta_reports_finding() -> None:
    findings = run_rules(
        SignalBundle(
            signals=[
                CapabilitySignal(
                    id="sig-business-checkout",
                    kind="business_invariant_risk",
                    source_ref="src/checkout/service.py",
                    confidence="medium",
                    evidence_refs=["src/checkout/service.py", ".riskmap.yml"],
                    attributes={
                        "issue_type": "critical_flow_changed_without_check_delta",
                        "flow_id": "checkout",
                        "changed_flow_file_count": "1",
                        "example_files": "src/checkout/service.py",
                        "check_terms": "checkout",
                        "spec_path": ".riskmap.yml",
                    },
                )
            ],
            supported_kinds={"business_invariant_risk"},
        )
    )

    assert any(row.rule_id == "business_critical_flow_changed_without_check_delta" for row in findings.findings)
