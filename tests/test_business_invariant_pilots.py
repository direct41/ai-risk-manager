from __future__ import annotations

from pathlib import Path
import shutil
from unittest.mock import patch

from ai_risk_manager.pipeline.run import run_pipeline
from ai_risk_manager.profiles.business_invariant import BusinessInvariantProfile
from ai_risk_manager.schemas.types import RunContext


PILOT_ROOT = Path("examples/business-invariants/pilots")


def _copy_pilot(tmp_path: Path, name: str) -> Path:
    repo_path = tmp_path / name
    shutil.copytree(PILOT_ROOT / name, repo_path)
    return repo_path


def _run_pr(repo_path: Path, changed_files: set[str], output_name: str):
    ctx = RunContext(
        repo_path=repo_path,
        mode="pr",
        base="main",
        output_dir=repo_path / output_name,
        provider="auto",
        no_llm=True,
    )
    with patch("ai_risk_manager.pipeline.run._resolve_changed_files", return_value=changed_files):
        return run_pipeline(ctx)


def test_checkout_service_pilot_covers_changed_and_checked_flow(tmp_path: Path) -> None:
    repo_path = _copy_pilot(tmp_path, "checkout-service")
    gap_result, gap_code, gap_notes = _run_pr(
        repo_path,
        {"app/checkout/service.py"},
        ".riskmap-gap",
    )
    covered_result, covered_code, _ = _run_pr(
        repo_path,
        {
            "app/checkout/service.py",
            "tests/integration/test_checkout.py",
        },
        ".riskmap-covered",
    )
    unmatched_result, unmatched_code, _ = _run_pr(
        repo_path,
        {"app/catalog/search.py"},
        ".riskmap-unmatched",
    )

    assert gap_code == covered_code == unmatched_code == 0
    assert gap_result is not None
    assert covered_result is not None
    assert unmatched_result is not None
    assert any(
        finding.rule_id == "business_critical_flow_changed_without_check_delta"
        for finding in gap_result.findings.findings
    )
    assert any("business_invariant_risk produced 1 PR-scoped signal" in note for note in gap_notes)
    assert not any(
        finding.rule_id == "business_critical_flow_changed_without_check_delta"
        for finding in covered_result.findings.findings
    )
    assert not any(
        finding.rule_id == "business_critical_flow_changed_without_check_delta"
        for finding in unmatched_result.findings.findings
    )


def test_support_console_pilot_normalizes_case_and_separators(tmp_path: Path) -> None:
    repo_path = _copy_pilot(tmp_path, "support-console")
    gap_result, gap_code, _ = _run_pr(
        repo_path,
        {"server/services/accountRecovery.js"},
        ".riskmap-gap",
    )
    covered_result, covered_code, _ = _run_pr(
        repo_path,
        {
            "server/services/accountRecovery.js",
            "tests/e2e/account-recovery.spec.js",
        },
        ".riskmap-covered",
    )

    assert gap_code == covered_code == 0
    assert gap_result is not None
    assert covered_result is not None
    assert any(
        finding.rule_id == "business_critical_flow_changed_without_check_delta"
        for finding in gap_result.findings.findings
    )
    assert not any(
        finding.rule_id == "business_critical_flow_changed_without_check_delta"
        for finding in covered_result.findings.findings
    )


def test_business_invariant_pilot_reports_malformed_spec_without_signal(tmp_path: Path) -> None:
    repo_path = tmp_path / "malformed"
    repo_path.mkdir()
    (repo_path / ".riskmap.yml").write_text(
        "critical_flows:\n  - match: [checkout]\n",
        encoding="utf-8",
    )
    profile = BusinessInvariantProfile()
    prepared = profile.prepare(repo_path, [])

    assessment = profile.assess_changed_scope(
        prepared,
        repo_path,
        {"app/checkout/service.py"},
    )

    assert prepared.applicability == "partial"
    assert assessment.signals.signals == []
    assert assessment.notes == [
        "business_invariant_risk found .riskmap.yml but no readable critical_flows entries."
    ]


def test_business_invariant_pilot_is_not_applicable_without_spec(tmp_path: Path) -> None:
    profile = BusinessInvariantProfile()
    prepared = profile.prepare(tmp_path, [])

    assessment = profile.assess_changed_scope(
        prepared,
        tmp_path,
        {"app/checkout/service.py"},
    )

    assert prepared.applicability == "not_applicable"
    assert assessment.notes == []
    assert assessment.signals.signals == []
