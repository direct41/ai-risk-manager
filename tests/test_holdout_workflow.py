from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "holdout_workflow.py"
SPEC = importlib.util.spec_from_file_location("holdout_workflow", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
holdout_workflow = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = holdout_workflow
SPEC.loader.exec_module(holdout_workflow)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _holdout_state() -> dict:
    return {
        "status": "not_established",
        "protocol_version": 1,
        "minimum_cases": 2,
        "minimum_independent_labelers": 2,
        "minimum_overlap_cases": 1,
        "frozen": False,
        "cases_path": None,
        "cases_sha256": None,
        "predictions_path": None,
        "predictions_sha256": None,
        "labels_path": None,
        "labels_sha256": None,
        "release_claim_blocked": True,
    }


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    manifest_path = tmp_path / "eval" / "dataset_manifest.json"
    _write_json(manifest_path, {"version": 2, "holdout": _holdout_state()})
    regression_path = tmp_path / "eval" / "public_prs.json"
    _write_json(regression_path, {"dataset_role": "regression", "cases": []})
    return manifest_path, regression_path


def _candidates() -> dict:
    return {
        "dataset_role": "holdout_candidates",
        "cases": [
            {
                "id": f"case-{index}",
                "url": f"https://github.com/example/project/pull/{index + 1}",
                "head_sha": f"{index + 1:040x}",
                "stack": "fastapi_pytest",
                "selected_at": "2026-06-20",
            }
            for index in range(2)
        ],
    }


def _freeze_cases(tmp_path: Path) -> tuple[Path, Path]:
    manifest_path, regression_path = _repo(tmp_path)
    candidate_path = tmp_path / "candidates.json"
    output_path = tmp_path / "eval" / "holdout" / "cases.json"
    _write_json(candidate_path, _candidates())
    digest = holdout_workflow.freeze_cases(
        candidate_path, output_path, manifest_path, regression_path, repo_root=tmp_path
    )
    assert digest == hashlib.sha256(output_path.read_bytes()).hexdigest()
    return manifest_path, output_path


def _write_success_result(path: Path, *, decision: str = "review_required") -> None:
    _write_json(
        path / "pr_summary.json",
        {"decision": decision, "top_findings": [{"rule_id": "rule-a"}, {"rule_id": "rule-a"}]},
    )
    _write_json(path / "merge_triage.json", {"decision": decision})
    _write_json(path / "findings.json", {"findings": [{"rule_id": "rule-a"}, {"rule_id": "rule-b"}]})


def test_freeze_cases_updates_manifest_and_writes_blind_packet(tmp_path: Path) -> None:
    manifest_path, cases_path = _freeze_cases(tmp_path)

    packet = json.loads(cases_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert packet == {"version": 1, "dataset_role": "holdout", "cases": _candidates()["cases"]}
    assert manifest["holdout"]["status"] == "cases_frozen"
    assert manifest["holdout"]["cases_path"] == "eval/holdout/cases.json"
    assert manifest["holdout"]["frozen"] is True
    assert manifest["holdout"]["release_claim_blocked"] is True


def test_cli_freeze_cases_uses_manifest_repository_root(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    manifest_path, regression_path = _repo(tmp_path)
    candidate_path = tmp_path / "intake" / "candidates.json"
    output_path = tmp_path / "eval" / "holdout" / "cases.json"
    _write_json(candidate_path, _candidates())

    exit_code = holdout_workflow.main(
        [
            "--manifest",
            str(manifest_path),
            "freeze-cases",
            "--input",
            str(candidate_path),
            "--output",
            str(output_path),
            "--regression",
            str(regression_path),
        ]
    )

    assert exit_code == 0
    assert output_path.is_file()
    assert "Holdout artifact created:" in capsys.readouterr().out


def test_freeze_cases_rejects_regression_reuse_and_forbidden_fields(tmp_path: Path) -> None:
    manifest_path, regression_path = _repo(tmp_path)
    candidate_path = tmp_path / "candidates.json"
    output_path = tmp_path / "eval" / "holdout" / "cases.json"
    candidates = _candidates()
    _write_json(regression_path, {"cases": [{"url": candidates["cases"][0]["url"]}]})
    _write_json(candidate_path, candidates)

    with pytest.raises(holdout_workflow.HoldoutWorkflowError, match="reuses regression"):
        holdout_workflow.freeze_cases(
            candidate_path, output_path, manifest_path, regression_path, repo_root=tmp_path
        )

    candidates["cases"][0]["expected"] = "ready"
    _write_json(regression_path, {"cases": []})
    _write_json(candidate_path, candidates)
    with pytest.raises(holdout_workflow.HoldoutWorkflowError, match="exactly"):
        holdout_workflow.freeze_cases(
            candidate_path, output_path, manifest_path, regression_path, repo_root=tmp_path
        )


def test_freeze_cases_refuses_overwrite_without_mutating_manifest(tmp_path: Path) -> None:
    manifest_path, regression_path = _repo(tmp_path)
    candidate_path = tmp_path / "candidates.json"
    output_path = tmp_path / "eval" / "holdout" / "cases.json"
    _write_json(candidate_path, _candidates())
    output_path.parent.mkdir(parents=True)
    output_path.write_text("existing", encoding="utf-8")
    original_manifest = manifest_path.read_bytes()

    with pytest.raises(holdout_workflow.HoldoutWorkflowError, match="refusing to overwrite"):
        holdout_workflow.freeze_cases(
            candidate_path, output_path, manifest_path, regression_path, repo_root=tmp_path
        )

    assert output_path.read_text(encoding="utf-8") == "existing"
    assert manifest_path.read_bytes() == original_manifest


def test_freeze_cases_removes_new_artifact_when_manifest_update_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, regression_path = _repo(tmp_path)
    candidate_path = tmp_path / "candidates.json"
    output_path = tmp_path / "eval" / "holdout" / "cases.json"
    _write_json(candidate_path, _candidates())

    def fail_manifest(path: Path, payload: object) -> None:
        raise OSError("simulated manifest failure")

    monkeypatch.setattr(holdout_workflow, "_write_json", fail_manifest)

    with pytest.raises(OSError, match="simulated manifest failure"):
        holdout_workflow.freeze_cases(
            candidate_path, output_path, manifest_path, regression_path, repo_root=tmp_path
        )

    assert not output_path.exists()
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["holdout"]["status"] == "not_established"


def test_freeze_predictions_collects_success_and_failure_results(tmp_path: Path) -> None:
    manifest_path, _ = _freeze_cases(tmp_path)
    results_dir = tmp_path / "results"
    _write_success_result(results_dir / "case-0")
    _write_json(results_dir / "case-1" / "execution.json", {"execution": "timeout"})
    output_path = tmp_path / "eval" / "holdout" / "predictions.json"

    digest = holdout_workflow.freeze_predictions(
        results_dir, output_path, manifest_path, "a" * 40, repo_root=tmp_path
    )

    packet = json.loads(output_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert digest == hashlib.sha256(output_path.read_bytes()).hexdigest()
    assert packet["generated_from_commit"] == "a" * 40
    assert packet["predictions"][0]["execution"] == "pass"
    assert packet["predictions"][0]["top_rules"] == ["rule-a"]
    assert packet["predictions"][0]["finding_count"] == 2
    assert packet["predictions"][1]["execution"] == "timeout"
    assert packet["predictions"][1]["decision"] is None
    assert manifest["holdout"]["status"] == "predictions_frozen"
    assert manifest["holdout"]["predictions_sha256"] == digest
    assert manifest["holdout"]["release_claim_blocked"] is True


def test_freeze_predictions_rejects_hash_drift_missing_artifacts_and_bad_commit(tmp_path: Path) -> None:
    manifest_path, cases_path = _freeze_cases(tmp_path)
    results_dir = tmp_path / "results"
    cases_path.write_text(cases_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(holdout_workflow.HoldoutWorkflowError, match="hash has drifted"):
        holdout_workflow.freeze_predictions(
            results_dir,
            tmp_path / "eval" / "holdout" / "predictions.json",
            manifest_path,
            "a" * 40,
            repo_root=tmp_path,
        )

    with pytest.raises(holdout_workflow.HoldoutWorkflowError, match="source commit"):
        holdout_workflow.freeze_predictions(
            results_dir,
            tmp_path / "eval" / "holdout" / "predictions.json",
            manifest_path,
            "main",
            repo_root=tmp_path,
        )


def test_create_label_template_contains_no_predictions(tmp_path: Path) -> None:
    manifest_path, _ = _freeze_cases(tmp_path)
    results_dir = tmp_path / "results"
    _write_success_result(results_dir / "case-0", decision="ready")
    _write_success_result(results_dir / "case-1", decision="block_recommended")
    predictions_path = tmp_path / "eval" / "holdout" / "predictions.json"
    holdout_workflow.freeze_predictions(
        results_dir, predictions_path, manifest_path, "b" * 40, repo_root=tmp_path
    )
    template_path = tmp_path / "reviewer-a.json"

    holdout_workflow.create_label_template(manifest_path, template_path, "reviewer-a", repo_root=tmp_path)

    template = json.loads(template_path.read_text(encoding="utf-8"))
    assert template["dataset_role"] == "holdout_label_template"
    assert [label["id"] for label in template["labels"]] == ["case-0", "case-1"]
    assert all(label["reviewer"] == "reviewer-a" for label in template["labels"])
    assert all(label["outcome"] is None and label["expected_decision"] is None for label in template["labels"])
    assert "ready" not in template_path.read_text(encoding="utf-8")
