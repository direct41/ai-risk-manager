from __future__ import annotations

from pathlib import Path
from typing import cast

from ai_risk_manager.rules.policy import apply_policy, is_blocking_enabled_for_finding, load_policy
from ai_risk_manager.schemas.types import Finding, FindingsReport, Severity


def _finding(*, rule_id: str = "critical_path_no_tests", severity: str = "high") -> Finding:
    return Finding(
        id=f"{rule_id}:id",
        rule_id=rule_id,
        title="t",
        description="d",
        severity=cast(Severity, severity),
        confidence="high",
        evidence="e",
        source_ref="app/api.py:1",
        suppression_key=f"{rule_id}:id",
        recommendation="r",
        evidence_refs=["app/api.py:1"],
    )


def test_load_policy_missing_file_returns_defaults(tmp_path: Path) -> None:
    policy, notes = load_policy(tmp_path / ".airiskpolicy")
    assert policy.rules == {}
    assert notes == []


def test_load_policy_invalid_payload_falls_back_with_note(tmp_path: Path) -> None:
    path = tmp_path / ".airiskpolicy"
    path.write_text("{ not-json", encoding="utf-8")
    policy, notes = load_policy(path)
    assert policy.rules == {}
    assert any("Ignoring invalid policy file" in note for note in notes)


def test_load_policy_parses_rule_overrides(tmp_path: Path) -> None:
    path = tmp_path / ".airiskpolicy"
    path.write_text(
        (
            "{"
            "\"version\": 1,"
            "\"rules\": {"
            "\"critical_path_no_tests\": {\"enabled\": true, \"severity\": \"medium\", \"gate\": \"never_block\"}"
            "}"
            "}"
        ),
        encoding="utf-8",
    )
    policy, notes = load_policy(path)
    assert "critical_path_no_tests" in policy.rules
    rule = policy.rules["critical_path_no_tests"]
    assert rule.enabled is True
    assert rule.severity == "medium"
    assert rule.gate == "never_block"
    assert any("Loaded policy" in note for note in notes)


def test_apply_policy_filters_and_overrides_severity(tmp_path: Path) -> None:
    path = tmp_path / ".airiskpolicy"
    path.write_text(
        (
            "{"
            "\"version\": 1,"
            "\"rules\": {"
            "\"critical_path_no_tests\": {\"enabled\": false},"
            "\"missing_transition_handler\": {\"severity\": \"critical\"}"
            "}"
            "}"
        ),
        encoding="utf-8",
    )
    policy, _ = load_policy(path)
    report = FindingsReport(findings=[_finding(rule_id="critical_path_no_tests"), _finding(rule_id="missing_transition_handler", severity="medium")])
    applied, dropped, overrides = apply_policy(report, policy)

    assert dropped == 1
    assert overrides == 1
    assert len(applied.findings) == 1
    assert applied.findings[0].rule_id == "missing_transition_handler"
    assert applied.findings[0].severity == "critical"


def test_is_blocking_enabled_respects_gate_override(tmp_path: Path) -> None:
    path = tmp_path / ".airiskpolicy"
    path.write_text(
        (
            "{"
            "\"version\": 1,"
            "\"rules\": {"
            "\"critical_path_no_tests\": {\"gate\": \"never_block\"}"
            "}"
            "}"
        ),
        encoding="utf-8",
    )
    policy, _ = load_policy(path)
    finding = _finding(rule_id="critical_path_no_tests")
    assert is_blocking_enabled_for_finding(policy, finding) is False
