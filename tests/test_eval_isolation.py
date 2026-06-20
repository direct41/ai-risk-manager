from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_eval_isolation.py"
SPEC = importlib.util.spec_from_file_location("check_eval_isolation", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
check_eval_isolation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = check_eval_isolation
SPEC.loader.exec_module(check_eval_isolation)


def _write_json(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cases_payload(count: int = 30, *, extra_field: bool = False) -> dict:
    cases = []
    for index in range(count):
        case = {
            "id": f"case-{index:02d}",
            "url": f"https://github.com/example/project/pull/{index + 1}",
            "head_sha": f"{index + 1:040x}",
            "stack": "fastapi_pytest",
            "selected_at": "2026-06-20",
        }
        if extra_field:
            case["expected"] = {"decision": "ready"}
        cases.append(case)
    return {"version": 1, "dataset_role": "holdout", "cases": cases}


def _manifest(holdout: dict) -> dict:
    return {
        "version": 2,
        "datasets": [
            {"path": "eval/repos", "role": "tuning", "purpose": "fixtures", "frozen": False},
            {"path": "eval/public_prs.json", "role": "regression", "purpose": "regression", "frozen": False},
        ],
        "holdout": holdout,
    }


def _holdout_state(**overrides: object) -> dict:
    payload = {
        "status": "not_established",
        "protocol_version": 1,
        "minimum_cases": 30,
        "minimum_independent_labelers": 2,
        "minimum_overlap_cases": 10,
        "frozen": False,
        "cases_path": None,
        "cases_sha256": None,
        "predictions_path": None,
        "predictions_sha256": None,
        "labels_path": None,
        "labels_sha256": None,
        "release_claim_blocked": True,
    }
    payload.update(overrides)
    return payload


def _write_manifest(repo_root: Path, holdout: dict) -> Path:
    path = repo_root / "eval" / "dataset_manifest.json"
    _write_json(path, _manifest(holdout))
    return path


def test_repository_dataset_manifest_passes_isolation_gate() -> None:
    assert check_eval_isolation.validate_manifest() == []


def test_not_established_holdout_cannot_reference_artifacts(tmp_path: Path) -> None:
    (tmp_path / "eval" / "repos").mkdir(parents=True)
    _write_json(tmp_path / "eval" / "public_prs.json", {"dataset_role": "regression"})
    manifest_path = _write_manifest(tmp_path, _holdout_state(cases_path="eval/holdout/cases.json"))

    errors = check_eval_isolation.validate_manifest(manifest_path, tmp_path)

    assert any("not_established holdout cannot reference" in error for error in errors)


def test_cases_frozen_accepts_minimum_blind_case_manifest(tmp_path: Path) -> None:
    (tmp_path / "eval" / "repos").mkdir(parents=True)
    _write_json(tmp_path / "eval" / "public_prs.json", {"dataset_role": "regression"})
    cases_path = tmp_path / "eval" / "holdout" / "cases.json"
    cases_sha = _write_json(cases_path, _cases_payload())
    manifest_path = _write_manifest(
        tmp_path,
        _holdout_state(
            status="cases_frozen",
            frozen=True,
            cases_path="eval/holdout/cases.json",
            cases_sha256=cases_sha,
        ),
    )

    assert check_eval_isolation.validate_manifest(manifest_path, tmp_path) == []


def test_cases_frozen_rejects_labels_or_expectations_in_case_records(tmp_path: Path) -> None:
    (tmp_path / "eval" / "repos").mkdir(parents=True)
    _write_json(tmp_path / "eval" / "public_prs.json", {"dataset_role": "regression"})
    cases_path = tmp_path / "eval" / "holdout" / "cases.json"
    cases_sha = _write_json(cases_path, _cases_payload(extra_field=True))
    manifest_path = _write_manifest(
        tmp_path,
        _holdout_state(
            status="cases_frozen",
            frozen=True,
            cases_path="eval/holdout/cases.json",
            cases_sha256=cases_sha,
        ),
    )

    errors = check_eval_isolation.validate_manifest(manifest_path, tmp_path)

    assert any("forbidden or unknown fields" in error for error in errors)


def test_cases_frozen_rejects_small_or_hash_drifted_dataset(tmp_path: Path) -> None:
    (tmp_path / "eval" / "repos").mkdir(parents=True)
    _write_json(tmp_path / "eval" / "public_prs.json", {"dataset_role": "regression"})
    cases_path = tmp_path / "eval" / "holdout" / "cases.json"
    _write_json(cases_path, _cases_payload(count=2))
    manifest_path = _write_manifest(
        tmp_path,
        _holdout_state(
            status="cases_frozen",
            frozen=True,
            cases_path="eval/holdout/cases.json",
            cases_sha256="0" * 64,
        ),
    )

    errors = check_eval_isolation.validate_manifest(manifest_path, tmp_path)

    assert any("requires at least 30 cases" in error for error in errors)
    assert any("cases_sha256 mismatch" in error for error in errors)


def test_predictions_frozen_binds_every_case_to_source_commit(tmp_path: Path) -> None:
    (tmp_path / "eval" / "repos").mkdir(parents=True)
    _write_json(tmp_path / "eval" / "public_prs.json", {"dataset_role": "regression"})
    cases_payload = _cases_payload()
    cases_path = tmp_path / "eval" / "holdout" / "cases.json"
    cases_sha = _write_json(cases_path, cases_payload)
    predictions = {
        "version": 1,
        "dataset_role": "holdout_predictions",
        "cases_sha256": cases_sha,
        "generated_from_commit": "a" * 40,
        "predictions": [
            {
                "id": case["id"],
                "execution": "pass",
                "decision": "ready",
                "top_rules": [],
                "finding_count": 0,
                "artifact_hash": "b" * 64,
            }
            for case in cases_payload["cases"]
        ],
    }
    predictions_path = tmp_path / "eval" / "holdout" / "predictions.json"
    predictions_sha = _write_json(predictions_path, predictions)
    manifest_path = _write_manifest(
        tmp_path,
        _holdout_state(
            status="predictions_frozen",
            frozen=True,
            cases_path="eval/holdout/cases.json",
            cases_sha256=cases_sha,
            predictions_path="eval/holdout/predictions.json",
            predictions_sha256=predictions_sha,
        ),
    )

    assert check_eval_isolation.validate_manifest(manifest_path, tmp_path) == []


def test_predictions_frozen_rejects_incomplete_or_inconsistent_rows(tmp_path: Path) -> None:
    (tmp_path / "eval" / "repos").mkdir(parents=True)
    _write_json(tmp_path / "eval" / "public_prs.json", {"dataset_role": "regression"})
    cases_payload = _cases_payload()
    cases_path = tmp_path / "eval" / "holdout" / "cases.json"
    cases_sha = _write_json(cases_path, cases_payload)
    predictions = {
        "dataset_role": "holdout_predictions",
        "cases_sha256": cases_sha,
        "generated_from_commit": "a" * 40,
        "predictions": [
            {
                "id": case["id"],
                "execution": "timeout",
                "decision": "ready",
                "top_rules": ["duplicate", "duplicate"],
                "finding_count": -1,
                "artifact_hash": "invalid",
            }
            for case in cases_payload["cases"]
        ],
    }
    predictions_path = tmp_path / "eval" / "holdout" / "predictions.json"
    predictions_sha = _write_json(predictions_path, predictions)
    manifest_path = _write_manifest(
        tmp_path,
        _holdout_state(
            status="predictions_frozen",
            frozen=True,
            cases_path="eval/holdout/cases.json",
            cases_sha256=cases_sha,
            predictions_path="eval/holdout/predictions.json",
            predictions_sha256=predictions_sha,
        ),
    )

    errors = check_eval_isolation.validate_manifest(manifest_path, tmp_path)

    assert any("cannot include a decision after failed execution" in error for error in errors)
    assert any("duplicate top_rules" in error for error in errors)
    assert any("non-negative finding_count" in error for error in errors)
    assert any("artifact_hash SHA-256" in error for error in errors)


def test_evaluated_holdout_requires_independent_reviewer_overlap(tmp_path: Path) -> None:
    (tmp_path / "eval" / "repos").mkdir(parents=True)
    _write_json(tmp_path / "eval" / "public_prs.json", {"dataset_role": "regression"})
    cases_payload = _cases_payload()
    cases_path = tmp_path / "eval" / "holdout" / "cases.json"
    cases_sha = _write_json(cases_path, cases_payload)
    predictions_path = tmp_path / "eval" / "holdout" / "predictions.json"
    predictions_sha = _write_json(
        predictions_path,
        {
            "dataset_role": "holdout_predictions",
            "cases_sha256": cases_sha,
            "generated_from_commit": "a" * 40,
            "predictions": [
                {
                    "id": case["id"],
                    "execution": "pass",
                    "decision": "ready",
                    "top_rules": [],
                    "finding_count": 0,
                    "artifact_hash": "b" * 64,
                }
                for case in cases_payload["cases"]
            ],
        },
    )
    labels = []
    for index, case in enumerate(cases_payload["cases"]):
        labels.append(
            {
                "id": case["id"],
                "reviewer": "reviewer-a",
                "outcome": "good_signal",
                "expected_decision": "ready",
                "rationale": "blind review",
                "reviewed_at": "2026-06-20",
            }
        )
        if index < 9:
            labels.append({**labels[-1], "reviewer": "reviewer-b"})
    labels_path = tmp_path / "eval" / "holdout" / "labels.json"
    labels_sha = _write_json(
        labels_path,
        {
            "dataset_role": "holdout_labels",
            "cases_sha256": cases_sha,
            "predictions_sha256": predictions_sha,
            "labels": labels,
        },
    )
    manifest_path = _write_manifest(
        tmp_path,
        _holdout_state(
            status="evaluated",
            frozen=True,
            cases_path="eval/holdout/cases.json",
            cases_sha256=cases_sha,
            predictions_path="eval/holdout/predictions.json",
            predictions_sha256=predictions_sha,
            labels_path="eval/holdout/labels.json",
            labels_sha256=labels_sha,
        ),
    )

    errors = check_eval_isolation.validate_manifest(manifest_path, tmp_path)

    assert any("at least 10 double-reviewed cases" in error for error in errors)

    case_nine_label = next(label for label in labels if label["id"] == "case-09")
    labels.append({**case_nine_label, "reviewer": "reviewer-b"})
    labels_sha = _write_json(
        labels_path,
        {
            "dataset_role": "holdout_labels",
            "cases_sha256": cases_sha,
            "predictions_sha256": predictions_sha,
            "labels": labels,
        },
    )
    manifest_path = _write_manifest(
        tmp_path,
        _holdout_state(
            status="evaluated",
            frozen=True,
            cases_path="eval/holdout/cases.json",
            cases_sha256=cases_sha,
            predictions_path="eval/holdout/predictions.json",
            predictions_sha256=predictions_sha,
            labels_path="eval/holdout/labels.json",
            labels_sha256=labels_sha,
        ),
    )

    assert check_eval_isolation.validate_manifest(manifest_path, tmp_path) == []


def test_change_isolation_rejects_holdout_and_analyzer_changes_together() -> None:
    errors = check_eval_isolation.validate_change_isolation(
        {"eval/holdout/cases.json", "eval/dataset_manifest.json", "src/ai_risk_manager/rules/engine.py"}
    )

    assert errors == ["holdout artifacts and analyzer/tuning/regression code cannot change in the same commit range"]

    gate_bypass_errors = check_eval_isolation.validate_change_isolation(
        {"eval/holdout/cases.json", "eval/dataset_manifest.json", "scripts/check_eval_isolation.py"}
    )
    assert gate_bypass_errors == errors
    workflow_bypass_errors = check_eval_isolation.validate_change_isolation(
        {"eval/holdout/cases.json", "eval/dataset_manifest.json", "scripts/holdout_workflow.py"}
    )
    assert workflow_bypass_errors == errors


def test_change_isolation_accepts_separate_holdout_or_analyzer_changes() -> None:
    assert check_eval_isolation.validate_change_isolation(
        {"eval/holdout/cases.json", "eval/dataset_manifest.json"}
    ) == []
    assert check_eval_isolation.validate_change_isolation({"src/ai_risk_manager/rules/engine.py"}) == []
