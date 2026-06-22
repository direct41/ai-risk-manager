from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from ai_risk_manager.pr_scope import (
    finding_matches_changed_files,
    is_pr_scoped_finding,
    normalize_path,
    source_ref_path,
)


@dataclass
class FindingStub:
    rule_id: str
    source_ref: str
    evidence_refs: list[str] = field(default_factory=list)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("./app/main.py", "app/main.py"),
        (".\\app\\main.py", "app/main.py"),
        ("  ././app/main.py  ", "app/main.py"),
        ("app/main.py", "app/main.py"),
    ],
)
def test_normalize_path_handles_repository_relative_variants(raw: str, expected: str) -> None:
    assert normalize_path(raw) == expected


@pytest.mark.parametrize(
    ("source_ref", "expected"),
    [
        ("app/main.py:12", "app/main.py"),
        ("app/main.py:0", "app/main.py"),
        ("app/main.py:not-a-line", "app/main.py:not-a-line"),
        ("C:/repo/app.py:7", "C:/repo/app.py"),
        ("app/main.py", "app/main.py"),
    ],
)
def test_source_ref_path_removes_only_numeric_line_suffix(source_ref: str, expected: str) -> None:
    assert source_ref_path(source_ref) == expected


def test_finding_matches_changed_files_checks_source_and_evidence_refs() -> None:
    source_match = FindingStub(rule_id="rule", source_ref="./app/main.py:12")
    evidence_match = FindingStub(
        rule_id="rule",
        source_ref="app/other.py:1",
        evidence_refs=["tests\\test_main.py:9"],
    )
    no_match = FindingStub(rule_id="rule", source_ref="app/other.py:1", evidence_refs=["README.md"])

    assert finding_matches_changed_files(source_match, {"app/main.py"}) is True
    assert finding_matches_changed_files(evidence_match, {"tests/test_main.py"}) is True
    assert finding_matches_changed_files(no_match, {"app/main.py"}) is False
    assert finding_matches_changed_files(source_match, set()) is False


def test_is_pr_scoped_finding_respects_rule_contract_and_changed_file_fallback() -> None:
    prefix_scoped = FindingStub(rule_id="pr_contract_change", source_ref="unrelated.py")
    explicit_scoped = FindingStub(rule_id="ui_journey_smoke_failed", source_ref="unrelated.py")
    changed_scoped = FindingStub(rule_id="generic_rule", source_ref="app/main.py:2")
    unscoped = FindingStub(rule_id="generic_rule", source_ref="app/other.py:2")

    assert is_pr_scoped_finding(prefix_scoped, set()) is True
    assert is_pr_scoped_finding(explicit_scoped, set()) is True
    assert is_pr_scoped_finding(changed_scoped, {"app/main.py"}) is True
    assert is_pr_scoped_finding(unscoped, {"app/main.py"}) is False
    assert is_pr_scoped_finding(changed_scoped, set()) is False
