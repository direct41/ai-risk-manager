from __future__ import annotations

from ai_risk_manager.rules.engine import run_rules
from ai_risk_manager.signals.types import CapabilitySignal, SignalBundle


def test_workflow_automation_reports_untrusted_context_to_shell() -> None:
    findings = run_rules(
        SignalBundle(
            signals=[
                CapabilitySignal(
                    id="sig-workflow-untrusted",
                    kind="workflow_automation_risk",
                    source_ref=".github/workflows/unsafe.yml:12",
                    confidence="high",
                    evidence_refs=[".github/workflows/unsafe.yml:12"],
                    attributes={
                        "issue_type": "untrusted_context_to_shell",
                        "owner_name": "Run agent on issue body",
                        "context_ref": "${{ github.event.issue.body }}",
                    },
                )
            ],
            supported_kinds={"workflow_automation_risk"},
        )
    )
    assert any(row.rule_id == "workflow_untrusted_context_to_shell" for row in findings.findings)


def test_workflow_automation_reports_external_action_not_pinned() -> None:
    findings = run_rules(
        SignalBundle(
            signals=[
                CapabilitySignal(
                    id="sig-workflow-unpinned",
                    kind="workflow_automation_risk",
                    source_ref=".github/workflows/unsafe.yml:4",
                    confidence="medium",
                    evidence_refs=[".github/workflows/unsafe.yml:4"],
                    attributes={
                        "issue_type": "external_action_not_pinned",
                        "owner_name": "Checkout",
                        "action_ref": "actions/checkout@v4",
                    },
                )
            ],
            supported_kinds={"workflow_automation_risk"},
        )
    )
    assert any(row.rule_id == "workflow_external_action_not_pinned" for row in findings.findings)
