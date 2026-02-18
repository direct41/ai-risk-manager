from __future__ import annotations

from pathlib import Path

from ai_risk_manager.rules.suppressions import apply_suppressions, load_suppressions
from ai_risk_manager.schemas.types import Finding, FindingsReport


def _finding(rule_id: str, source_ref: str, suppression_key: str) -> Finding:
    return Finding(
        id=f"{rule_id}:{source_ref}",
        rule_id=rule_id,
        title="title",
        description="desc",
        severity="medium",
        confidence="medium",
        evidence="e",
        source_ref=source_ref,
        suppression_key=suppression_key,
        recommendation="rec",
    )


def test_load_and_apply_suppressions_by_key_and_rule_file(tmp_path: Path) -> None:
    suppress_file = tmp_path / ".airiskignore"
    suppress_file.write_text(
        "- key: \"critical_path_no_tests:api:create_order\"\n"
        "- rule: \"missing_transition_handler\"\n"
        "  file: \"app/order.py\"\n",
        encoding="utf-8",
    )

    suppressions, _ = load_suppressions(suppress_file)
    findings = FindingsReport(
        findings=[
            _finding("critical_path_no_tests", "app/api.py", "critical_path_no_tests:api:create_order"),
            _finding("missing_transition_handler", "app/order.py", "k2"),
            _finding("missing_transition_handler", "app/other.py", "k3"),
        ]
    )

    filtered, suppressed_count = apply_suppressions(findings, suppressions)
    assert suppressed_count == 2
    assert len(filtered.findings) == 1
    assert filtered.findings[0].source_ref == "app/other.py"


def test_load_suppressions_ignores_malformed_lines(tmp_path: Path) -> None:
    suppress_file = tmp_path / ".airiskignore"
    suppress_file.write_text("oops\n- key: \"x\"\n", encoding="utf-8")

    suppressions, notes = load_suppressions(suppress_file)
    assert "x" in suppressions.keys
    assert any("malformed suppression line" in note for note in notes)
