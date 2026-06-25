from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "holdout_reporting.py"
MODULE_NAME = "holdout_reporting"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
holdout_reporting = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = holdout_reporting
SPEC.loader.exec_module(holdout_reporting)


@pytest.fixture(autouse=True)
def _cleanup_sys_modules() -> None:
    yield
    sys.modules.pop(MODULE_NAME, None)


def _label(case_id: str, reviewer: str, *, decision: str = "ready") -> dict:
    return {
        "id": case_id,
        "reviewer": reviewer,
        "expected_decision": decision,
        "rationale": "independent review",
        "reviewed_at": "2026-06-22",
    }


def _packet(reviewer: str, case_ids: list[str]) -> dict:
    return {
        "version": 1,
        "dataset_role": "holdout_label_template",
        "cases_sha256": "a" * 64,
        "predictions_sha256": "b" * 64,
        "labels": [_label(case_id, reviewer) for case_id in case_ids],
    }


def test_merge_reviewer_packets_requires_coverage_and_overlap() -> None:
    labels = holdout_reporting.merge_reviewer_packets(
        [_packet("reviewer-a", ["case-1", "case-2"]), _packet("reviewer-b", ["case-1"])],
        cases_sha256="a" * 64,
        predictions_sha256="b" * 64,
        case_ids={"case-1", "case-2"},
        minimum_reviewers=2,
        minimum_overlap_cases=1,
    )

    assert [(label["id"], label["reviewer"]) for label in labels] == [
        ("case-1", "reviewer-a"),
        ("case-1", "reviewer-b"),
        ("case-2", "reviewer-a"),
    ]

    with pytest.raises(holdout_reporting.HoldoutReportingError, match="every holdout case"):
        holdout_reporting.merge_reviewer_packets(
            [_packet("reviewer-a", ["case-1"]), _packet("reviewer-b", ["case-1"])],
            cases_sha256="a" * 64,
            predictions_sha256="b" * 64,
            case_ids={"case-1", "case-2"},
            minimum_reviewers=2,
            minimum_overlap_cases=1,
        )


def test_merge_reviewer_packets_rejects_incomplete_or_duplicate_labels() -> None:
    packet_a = _packet("reviewer-a", ["case-1"])
    packet_a["labels"][0]["expected_decision"] = None
    with pytest.raises(holdout_reporting.HoldoutReportingError, match="incomplete"):
        holdout_reporting.merge_reviewer_packets(
            [packet_a, _packet("reviewer-b", ["case-1"])],
            cases_sha256="a" * 64,
            predictions_sha256="b" * 64,
            case_ids={"case-1"},
            minimum_reviewers=2,
            minimum_overlap_cases=1,
        )

    duplicate = _packet("reviewer-a", ["case-1"])
    with pytest.raises(holdout_reporting.HoldoutReportingError, match="duplicate reviewer label"):
        holdout_reporting.merge_reviewer_packets(
            [duplicate, duplicate, _packet("reviewer-b", ["case-1"])],
            cases_sha256="a" * 64,
            predictions_sha256="b" * 64,
            case_ids={"case-1"},
            minimum_reviewers=2,
            minimum_overlap_cases=1,
        )


def test_disagreements_require_exact_adjudication() -> None:
    labels = [_label("case-1", "reviewer-a"), _label("case-1", "reviewer-b", decision="review_required")]

    with pytest.raises(holdout_reporting.HoldoutReportingError, match="adjudication is required"):
        holdout_reporting.validate_adjudications(
            None, labels=labels, cases_sha256="a" * 64, predictions_sha256="b" * 64
        )

    packet = {
        "version": 1,
        "dataset_role": "holdout_adjudications",
        "cases_sha256": "a" * 64,
        "predictions_sha256": "b" * 64,
        "adjudications": [
            {
                "id": "case-1",
                "adjudicator": "reviewer-c",
                "expected_decision": "review_required",
                "rationale": "resolved from PR evidence",
                "reviewed_at": "2026-06-22",
            }
        ],
    }

    assert holdout_reporting.validate_adjudications(
        packet, labels=labels, cases_sha256="a" * 64, predictions_sha256="b" * 64
    ) == packet["adjudications"]


def test_build_report_calculates_confusion_agreement_and_stack_breakdown() -> None:
    labels = [
        _label("case-1", "reviewer-a", decision="ready"),
        _label("case-1", "reviewer-b", decision="ready"),
        _label("case-2", "reviewer-a", decision="review_required"),
        _label("case-2", "reviewer-b", decision="block_recommended"),
    ]
    labels_packet = {
        "cases_sha256": "a" * 64,
        "predictions_sha256": "b" * 64,
        "labels": labels,
        "adjudications": [
            {
                "id": "case-2",
                "adjudicator": "reviewer-c",
                "expected_decision": "block_recommended",
                "rationale": "resolved",
                "reviewed_at": "2026-06-22",
            }
        ],
    }
    report = holdout_reporting.build_report(
        cases_packet={
            "cases": [
                {"id": "case-1", "stack": "fastapi_pytest"},
                {"id": "case-2", "stack": "express_node"},
            ]
        },
        predictions_packet={
            "generated_from_commit": "c" * 40,
            "predictions": [
                {"id": "case-1", "execution": "pass", "decision": "ready"},
                {"id": "case-2", "execution": "pass", "decision": "review_required"},
            ],
        },
        labels_packet=labels_packet,
        labels_sha256="d" * 64,
    )

    assert report["decision"]["confusion_matrix"]["ready"]["ready"] == 1
    assert report["decision"]["confusion_matrix"]["block_recommended"]["review_required"] == 1
    assert report["decision"]["exact_match_rate"] == 0.5
    assert report["agreement"]["expected_decision_raw_agreement"] == 0.5
    assert report["agreement"]["expected_decision_cohens_kappa"] == pytest.approx(1 / 3, abs=0.0001)
    assert report["outcomes"] == {
        "aligned": 1,
        "overcalled": 0,
        "undercalled": 1,
        "execution_failure": 0,
    }
    assert report["stacks"]["express_node"]["decision_matches"] == 0
    assert "blocked_pending_policy_thresholds" in holdout_reporting.render_report_markdown(report)
