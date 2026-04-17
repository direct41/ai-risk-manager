from __future__ import annotations

from ai_risk_manager.rules.engine import run_rules
from ai_risk_manager.signals.types import CapabilitySignal, SignalBundle


def test_ui_journey_smoke_failed_reports_finding() -> None:
    findings = run_rules(
        SignalBundle(
            signals=[
                CapabilitySignal(
                    id="sig-ui-smoke-checkout",
                    kind="ui_journey_smoke",
                    source_ref="src/pages/checkout.tsx",
                    confidence="high",
                    evidence_refs=["src/pages/checkout.tsx", ".riskmap-ui.toml"],
                    attributes={
                        "issue_type": "journey_smoke_failed",
                        "journey_id": "checkout",
                        "changed_journey": "checkout",
                        "command": "python3 -c 'raise SystemExit(2)'",
                        "exit_code": 2,
                        "output_excerpt": "boom",
                    },
                )
            ],
            supported_kinds={"ui_journey_smoke"},
        )
    )

    assert any(row.rule_id == "ui_journey_smoke_failed" for row in findings.findings)
