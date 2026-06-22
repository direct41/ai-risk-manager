from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_risk_manager.schemas.types import Finding
from ai_risk_manager.trust.outcomes import TrustOutcomeCounts, TrustOutcomes, load_trust_outcomes
from ai_risk_manager.trust import scoring
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
    assert trust.heuristic_trust_score >= 0.75
    assert trust.score_kind == "heuristic_trust"
    assert trust.calibrated is False
    assert trust.estimated_precision == trust.heuristic_trust_score


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


def _finding(
    *,
    confidence: str = "medium",
    origin: str = "deterministic",
    evidence_refs: list[str] | None = None,
    fingerprint: str = "fp",
) -> Finding:
    return Finding(
        id="boundary-finding",
        rule_id="boundary_rule",
        title="title",
        description="desc",
        severity="medium",
        confidence=confidence,
        evidence="evidence",
        source_ref="app.py:1",
        suppression_key="boundary-finding",
        recommendation="test it",
        origin=origin,
        fingerprint=fingerprint,
        evidence_refs=[] if evidence_refs is None else evidence_refs,
    )


@pytest.mark.parametrize(
    ("confidence", "expected_score", "expected_band"),
    [
        ("high", 0.94, "strong"),
        ("medium", 0.80, "strong"),
        ("low", 0.66, "moderate"),
    ],
)
def test_score_finding_confidence_boundaries_are_exact(
    tmp_path: Path,
    write_file,
    confidence: str,
    expected_score: float,
    expected_band: str,
) -> None:
    write_file(tmp_path / "app.py", "line one\nline two\n")
    write_file(tmp_path / "test_app.py", "line one\n")

    trust = score_finding(
        _finding(confidence=confidence, evidence_refs=["app.py:2", "test_app.py:1"]),
        repo_path=tmp_path,
        repository_support_state="supported",
        outcomes=TrustOutcomes(),
    )

    assert trust.score == expected_score
    assert trust.heuristic_trust_score == expected_score
    assert trust.estimated_precision == expected_score
    assert trust.band == expected_band
    assert trust.evidence_strength == "high"


@pytest.mark.parametrize(
    ("counts", "expected_signal", "expected_score"),
    [
        (TrustOutcomeCounts(actioned_count=2, accepted_count=1), "actioned_bias", 0.65),
        (TrustOutcomeCounts(accepted_count=2), "accepted_bias", 0.63),
        (TrustOutcomeCounts(suppressed_count=2), "suppressed_bias", 0.52),
        (TrustOutcomeCounts(accepted_count=1, suppressed_count=1), "neutral", 0.60),
    ],
)
def test_score_finding_history_deltas_are_exact(
    tmp_path: Path,
    counts: TrustOutcomeCounts,
    expected_signal: str,
    expected_score: float,
) -> None:
    finding = _finding(evidence_refs=[])

    trust = score_finding(
        finding,
        repo_path=tmp_path,
        repository_support_state="supported",
        outcomes=TrustOutcomes(by_fingerprint={"fp": counts}),
    )

    assert trust.score == expected_score
    assert trust.history_signal == expected_signal
    assert trust.evidence_strength == "low"


def test_score_finding_rejects_missing_line_as_verified_evidence(tmp_path: Path, write_file) -> None:
    write_file(tmp_path / "app.py", "only one line\n")

    trust = score_finding(
        _finding(evidence_refs=["app.py:2"]),
        repo_path=tmp_path,
        repository_support_state="supported",
        outcomes=TrustOutcomes(),
    )

    assert trust.evidence_strength == "low"
    assert trust.score == 0.61


def test_reference_resolution_preserves_paths_and_optional_lines(tmp_path: Path) -> None:
    relative_path, relative_line = scoring._resolve_ref_path_line(tmp_path, "nested/app.py:12")
    absolute = tmp_path / "absolute.py"
    absolute_path, absolute_line = scoring._resolve_ref_path_line(tmp_path, str(absolute))
    non_line_path, non_line = scoring._resolve_ref_path_line(tmp_path, "schema:v2")
    colon_path, colon_line = scoring._resolve_ref_path_line(tmp_path, "schema:v2:7")

    assert relative_path == tmp_path / "nested/app.py"
    assert relative_line == 12
    assert absolute_path == absolute
    assert absolute_line is None
    assert non_line_path == tmp_path / "schema:v2"
    assert non_line is None
    assert colon_path == tmp_path / "schema:v2"
    assert colon_line == 7


def test_reference_existence_checks_exact_line_boundaries(tmp_path: Path, write_file) -> None:
    write_file(tmp_path / "app.py", "first\nsecond\n")

    assert scoring._ref_exists(tmp_path, "app.py") is True
    assert scoring._ref_exists(tmp_path, "app.py:1") is True
    assert scoring._ref_exists(tmp_path, "app.py:2") is True
    assert scoring._ref_exists(tmp_path, "app.py:3") is False
    assert scoring._ref_exists(tmp_path, "missing.py") is False


def test_reference_read_error_is_not_treated_as_verified(
    tmp_path: Path,
    write_file,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "app.py"
    write_file(path, "first\n")

    def fail_open(*args: object, **kwargs: object) -> None:
        raise OSError("unreadable")

    monkeypatch.setattr(type(path), "open", fail_open)

    assert scoring._ref_exists(tmp_path, "app.py:1") is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [(-0.1, 0.0), (0.0, 0.0), (0.4, 0.4), (1.0, 1.0), (1.1, 1.0)],
)
def test_clamp_has_closed_zero_to_one_boundaries(value: float, expected: float) -> None:
    assert scoring._clamp(value) == expected


@pytest.mark.parametrize(
    ("score", "expected"),
    [(0.78, "strong"), (0.779, "moderate"), (0.6, "moderate"), (0.599, "weak")],
)
def test_trust_band_boundaries_are_exact(score: float, expected: str) -> None:
    assert scoring._band(score) == expected


def test_evidence_strength_counts_only_verified_references(tmp_path: Path, write_file) -> None:
    write_file(tmp_path / "app.py", "first\nsecond\n")

    assert scoring._evidence_strength(["missing.py"], tmp_path) == ("low", 0)
    assert scoring._evidence_strength(["app.py:1", "app.py:3"], tmp_path) == ("medium", 1)
    assert scoring._evidence_strength(["app.py:1", "app.py:2"], tmp_path) == ("high", 2)


def test_missing_reference_and_no_reference_have_distinct_penalties(tmp_path: Path) -> None:
    without_refs = score_finding(
        _finding(evidence_refs=[]),
        repo_path=tmp_path,
        repository_support_state="supported",
        outcomes=TrustOutcomes(),
    )
    with_missing_ref = score_finding(
        _finding(evidence_refs=["missing.py:1"]),
        repo_path=tmp_path,
        repository_support_state="supported",
        outcomes=TrustOutcomes(),
    )

    assert without_refs.score == 0.6
    assert with_missing_ref.score == 0.61
