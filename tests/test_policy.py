from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

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


@pytest.mark.parametrize(
    ("payload", "expected_note"),
    [
        ([], "top-level object is required"),
        ({"version": 2}, "expected version=1"),
        ({"version": 1, "rules": []}, "rules section"),
    ],
)
def test_load_policy_rejects_invalid_contract_shapes(
    tmp_path: Path,
    payload: object,
    expected_note: str,
) -> None:
    path = tmp_path / ".airiskpolicy"
    path.write_text(json.dumps(payload), encoding="utf-8")

    policy, notes = load_policy(path)

    assert policy.version == 1
    assert policy.rules == {}
    assert len(notes) == 1
    assert expected_note in notes[0]


def test_load_policy_keeps_rule_with_safe_defaults_for_invalid_fields(tmp_path: Path) -> None:
    path = tmp_path / ".airiskpolicy"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "rules": {
                    "critical_path_no_tests": {
                        "enabled": "no",
                        "severity": "urgent",
                        "gate": "always_block",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    policy, notes = load_policy(path)

    assert policy.rules["critical_path_no_tests"].enabled is True
    assert policy.rules["critical_path_no_tests"].severity is None
    assert policy.rules["critical_path_no_tests"].gate == "default"
    assert len([note for note in notes if "Ignoring policy field" in note]) == 3
    assert notes[-1].startswith("Loaded policy")


def test_apply_policy_preserves_input_report_and_generated_without_llm(tmp_path: Path) -> None:
    path = tmp_path / ".airiskpolicy"
    path.write_text(
        json.dumps({"version": 1, "rules": {"critical_path_no_tests": {"severity": "low"}}}),
        encoding="utf-8",
    )
    policy, _ = load_policy(path)
    original = _finding(severity="high")
    report = FindingsReport(findings=[original], generated_without_llm=True)

    applied, dropped, overrides = apply_policy(report, policy)

    assert dropped == 0
    assert overrides == 1
    assert original.severity == "high"
    assert applied.findings[0].severity == "low"
    assert applied.generated_without_llm is True


def test_is_blocking_enabled_defaults_to_true_and_disabled_rule_never_blocks(tmp_path: Path) -> None:
    finding = _finding()
    default_policy, _ = load_policy(None)
    assert is_blocking_enabled_for_finding(default_policy, finding) is True

    path = tmp_path / ".airiskpolicy"
    path.write_text(
        json.dumps({"version": 1, "rules": {finding.rule_id: {"enabled": False}}}),
        encoding="utf-8",
    )
    disabled_policy, _ = load_policy(path)
    assert is_blocking_enabled_for_finding(disabled_policy, finding) is False
