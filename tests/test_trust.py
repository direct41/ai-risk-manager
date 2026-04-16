from __future__ import annotations

import json
from pathlib import Path

from ai_risk_manager.schemas.types import Finding
from ai_risk_manager.trust.outcomes import TrustOutcomeCounts, TrustOutcomes, load_trust_outcomes
from ai_risk_manager.trust.scoring import annotate_finding_trust, score_finding


def test_score_finding_prefers_supported_deterministic_verified_evidence(tmp_path: Path, write_file) -> None:
    write_file(tmp_path / "app.py", "def mutate():\n    return True\n")
    finding = Finding(
        id="f1",
        rule_id="critical_path_no_tests",
        title="title",
        description="desc",
        severity="high",
        confidence="high",
        evidence="e",
        source_ref="app.py:1",
        suppression_key="f1",
        recommendation="rec",
        origin="deterministic",
        evidence_refs=["app.py:1"],
    )

    trust = score_finding(
        finding,
        repo_path=tmp_path,
        repository_support_state="supported",
        outcomes=TrustOutcomes(),
    )

    assert trust.band in {"strong", "moderate"}
    assert trust.estimated_precision >= 0.75


def test_score_finding_penalizes_suppressed_history_and_missing_evidence(tmp_path: Path) -> None:
    finding = Finding(
        id="f2",
        rule_id="pr_code_change_without_test_delta",
        title="title",
        description="desc",
        severity="medium",
        confidence="medium",
        evidence="e",
        source_ref="missing.py:1",
        suppression_key="f2",
        recommendation="rec",
        origin="ai",
        fingerprint="fp-1",
        evidence_refs=["missing.py:1"],
    )

    trust = score_finding(
        finding,
        repo_path=tmp_path,
        repository_support_state="partial",
        outcomes=TrustOutcomes(
            by_fingerprint={
                "fp-1": TrustOutcomeCounts(suppressed_count=3),
            }
        ),
    )

    assert trust.band == "weak"
    assert trust.history_signal == "suppressed_bias"


def test_load_trust_outcomes_reads_repo_local_file(tmp_path: Path) -> None:
    path = tmp_path / ".airisktrust.json"
    path.write_text(
        json.dumps(
            {
                "by_fingerprint": {"fp-1": {"suppressed_count": 2}},
                "by_rule_id": {"critical_path_no_tests": {"actioned_count": 1}},
            }
        ),
        encoding="utf-8",
    )

    outcomes, notes = load_trust_outcomes(path)

    assert outcomes.by_fingerprint["fp-1"].suppressed_count == 2
    assert outcomes.by_rule_id["critical_path_no_tests"].actioned_count == 1
    assert notes


def test_annotate_finding_trust_sets_trust_payload(tmp_path: Path, write_file) -> None:
    write_file(tmp_path / "service.py", "def mutate():\n    return True\n")
    finding = Finding(
        id="f3",
        rule_id="dependency_risk_policy_violation",
        title="title",
        description="desc",
        severity="medium",
        confidence="high",
        evidence="e",
        source_ref="service.py:1",
        suppression_key="f3",
        recommendation="rec",
        origin="deterministic",
        evidence_refs=["service.py:1"],
    )

    annotate_finding_trust(
        [finding],
        repo_path=tmp_path,
        repository_support_state="supported",
        outcomes=TrustOutcomes(),
    )

    assert finding.trust is not None
    assert finding.trust.band in {"strong", "moderate"}
