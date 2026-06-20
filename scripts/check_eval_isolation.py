from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess  # nosec B404
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "eval" / "dataset_manifest.json"
HOLDOUT_PREFIX = "eval/holdout/"
ANALYZER_PREFIXES = (
    "src/ai_risk_manager/",
    "eval/repos/",
)
ANALYZER_EXACT_PATHS = {
    ".github/workflows/quality.yml",
    "eval/public_prs.json",
    "scripts/check_eval_isolation.py",
    "scripts/holdout_workflow.py",
    "scripts/run_eval_suite.py",
}
HOLDOUT_PHASES = ("not_established", "cases_frozen", "predictions_frozen", "evaluated")
CASE_ALLOWED_FIELDS = {"id", "url", "head_sha", "stack", "selected_at"}
CASE_PACKET_ALLOWED_FIELDS = {"version", "dataset_role", "selection_policy", "cases"}
SELECTION_POLICY_ALLOWED_FIELDS = {
    "repositories",
    "per_repository",
    "states",
    "changed_files",
    "diff_size",
    "ordering",
    "excluded_dataset",
    "excluded_dataset_sha256",
    "selected_at",
}
PREDICTION_ALLOWED_FIELDS = {"id", "execution", "decision", "top_rules", "finding_count", "artifact_hash"}
LABEL_ALLOWED_FIELDS = {"id", "reviewer", "outcome", "expected_decision", "rationale", "reviewed_at"}
PREDICTION_EXECUTIONS = {"pass", "setup_fail", "provider_fail", "tool_fail", "artifact_fail", "timeout"}
MERGE_DECISIONS = {"ready", "review_required", "block_recommended"}
LABEL_OUTCOMES = {"good_signal", "noisy", "false_positive", "missed_risk"}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_repo_file(repo_root: Path, raw_path: object, *, label: str, errors: list[str]) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path.startswith(HOLDOUT_PREFIX):
        errors.append(f"{label} must be a repository-relative path under {HOLDOUT_PREFIX}")
        return None
    candidate = (repo_root / raw_path).resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError:
        errors.append(f"{label} escapes repository root")
        return None
    if not candidate.is_file():
        errors.append(f"{label} does not exist: {raw_path}")
        return None
    return candidate


def _validate_hash(path: Path, expected: object, *, label: str, errors: list[str]) -> None:
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        errors.append(f"{label} must be a lowercase SHA-256 digest")
        return
    observed = _sha256(path)
    if observed != expected:
        errors.append(f"{label} mismatch: expected {expected}, observed {observed}")


def _validate_cases(path: Path, *, minimum_cases: int, errors: list[str]) -> set[str]:
    try:
        payload = _read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"holdout cases are unreadable: {exc}")
        return set()
    if not isinstance(payload, dict) or payload.get("dataset_role") != "holdout":
        errors.append("holdout cases must be an object with dataset_role=holdout")
        return set()
    unexpected_packet_fields = sorted(set(payload) - CASE_PACKET_ALLOWED_FIELDS)
    if unexpected_packet_fields:
        errors.append(f"holdout cases packet contains unknown fields: {unexpected_packet_fields}")
    if payload.get("version") != 1:
        errors.append("holdout cases packet version must be 1")
    cases = payload.get("cases")
    if not isinstance(cases, list):
        errors.append("holdout cases must contain a cases list")
        return set()
    if len(cases) < minimum_cases:
        errors.append(f"holdout requires at least {minimum_cases} cases; found {len(cases)}")

    case_ids: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"holdout case {index} must be an object")
            continue
        unexpected = sorted(set(case) - CASE_ALLOWED_FIELDS)
        if unexpected:
            errors.append(f"holdout case {index} contains forbidden or unknown fields: {unexpected}")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            errors.append(f"holdout case {index} requires a non-empty id")
        elif case_id in case_ids:
            errors.append(f"duplicate holdout case id: {case_id}")
        else:
            case_ids.add(case_id)
        if not isinstance(case.get("head_sha"), str) or not re.fullmatch(r"[0-9a-f]{40}", case["head_sha"]):
            errors.append(f"holdout case {index} requires a lowercase 40-character head_sha")
        if not isinstance(case.get("url"), str) or not re.fullmatch(
            r"https://github\.com/[^/]+/[^/]+/pull/[1-9][0-9]*", case["url"]
        ):
            errors.append(f"holdout case {index} requires a canonical public GitHub PR URL")
    _validate_selection_policy(payload.get("selection_policy"), cases, errors=errors)
    return case_ids


def _validate_selection_policy(policy: object, cases: list[object], *, errors: list[str]) -> None:
    if not isinstance(policy, dict) or set(policy) != SELECTION_POLICY_ALLOWED_FIELDS:
        errors.append("holdout cases require a complete selection_policy")
        return
    repositories = policy.get("repositories")
    quota = policy.get("per_repository")
    if (
        not isinstance(repositories, list)
        or not repositories
        or not all(isinstance(repo, str) and re.fullmatch(r"[^/]+/[^/]+", repo) for repo in repositories)
        or len(repositories) != len(set(repositories))
    ):
        errors.append("selection_policy repositories must be unique owner/repository strings")
        return
    if not isinstance(quota, int) or isinstance(quota, bool) or quota < 1:
        errors.append("selection_policy per_repository must be a positive integer")
        return
    counts = {repository: 0 for repository in repositories}
    selected_at = policy.get("selected_at")
    for case in cases:
        if not isinstance(case, dict):
            continue
        url = case.get("url")
        match = re.match(r"https://github\.com/([^/]+/[^/]+)/pull/", url) if isinstance(url, str) else None
        repository = match.group(1) if match else ""
        if repository in counts:
            counts[repository] += 1
        if case.get("selected_at") != selected_at:
            errors.append("case selected_at values must match selection_policy selected_at")
            break
    if len(cases) != len(repositories) * quota or any(count != quota for count in counts.values()):
        errors.append("holdout cases must satisfy selection_policy repository quotas")
    if policy.get("states") != ["MERGED"]:
        errors.append("selection_policy states must be [MERGED]")
    for field in ("changed_files", "diff_size"):
        bounds = policy.get(field)
        if (
            not isinstance(bounds, list)
            or len(bounds) != 2
            or not all(isinstance(value, int) and not isinstance(value, bool) for value in bounds)
            or bounds[0] < 0
            or bounds[0] > bounds[1]
        ):
            errors.append(f"selection_policy {field} must be ordered non-negative integer bounds")
    if policy.get("ordering") != "most_recently_updated_eligible":
        errors.append("selection_policy ordering must be most_recently_updated_eligible")
    if policy.get("excluded_dataset") != "eval/public_prs.json":
        errors.append("selection_policy excluded_dataset must be eval/public_prs.json")
    excluded_hash = policy.get("excluded_dataset_sha256")
    if not isinstance(excluded_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", excluded_hash):
        errors.append("selection_policy excluded_dataset_sha256 must be a SHA-256")
    if not isinstance(selected_at, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", selected_at):
        errors.append("selection_policy selected_at must be an ISO date")


def _validate_predictions(path: Path, *, case_ids: set[str], cases_sha256: str, errors: list[str]) -> str | None:
    try:
        payload = _read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"holdout predictions are unreadable: {exc}")
        return None
    if not isinstance(payload, dict) or payload.get("dataset_role") != "holdout_predictions":
        errors.append("holdout predictions must have dataset_role=holdout_predictions")
        return None
    if payload.get("cases_sha256") != cases_sha256:
        errors.append("holdout predictions are not bound to the frozen cases SHA-256")
    commit = payload.get("generated_from_commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        errors.append("holdout predictions require generated_from_commit as a 40-character SHA")
    predictions = payload.get("predictions")
    if not isinstance(predictions, list):
        errors.append("holdout predictions must contain a predictions list")
        return None
    prediction_ids: set[str] = set()
    for index, prediction in enumerate(predictions):
        if not isinstance(prediction, dict):
            errors.append(f"holdout prediction {index} must be an object")
            continue
        unexpected = sorted(set(prediction) - PREDICTION_ALLOWED_FIELDS)
        if unexpected:
            errors.append(f"holdout prediction {index} contains unknown fields: {unexpected}")
        prediction_id = prediction.get("id")
        if isinstance(prediction_id, str) and prediction_id.strip():
            if prediction_id in prediction_ids:
                errors.append(f"duplicate holdout prediction id: {prediction_id}")
            prediction_ids.add(prediction_id)
        else:
            errors.append(f"holdout prediction {index} requires a non-empty id")
        if prediction.get("execution") not in PREDICTION_EXECUTIONS:
            errors.append(f"holdout prediction {index} has an invalid execution status")
        execution = prediction.get("execution")
        decision = prediction.get("decision")
        if decision is not None and decision not in MERGE_DECISIONS:
            errors.append(f"holdout prediction {index} has an invalid decision")
        if execution == "pass" and decision not in MERGE_DECISIONS:
            errors.append(f"holdout prediction {index} requires a decision after successful execution")
        if execution in PREDICTION_EXECUTIONS - {"pass"} and decision is not None:
            errors.append(f"holdout prediction {index} cannot include a decision after failed execution")
        top_rules = prediction.get("top_rules")
        if not isinstance(top_rules, list) or not all(isinstance(rule, str) and rule.strip() for rule in top_rules):
            errors.append(f"holdout prediction {index} requires a top_rules string list")
        elif len(top_rules) != len(set(top_rules)):
            errors.append(f"holdout prediction {index} contains duplicate top_rules")
        finding_count = prediction.get("finding_count")
        if not isinstance(finding_count, int) or isinstance(finding_count, bool) or finding_count < 0:
            errors.append(f"holdout prediction {index} requires a non-negative finding_count")
        artifact_hash = prediction.get("artifact_hash")
        if not isinstance(artifact_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", artifact_hash):
            errors.append(f"holdout prediction {index} requires an artifact_hash SHA-256")
    if prediction_ids != case_ids:
        errors.append("holdout prediction IDs must match frozen case IDs exactly")
    return _sha256(path)


def _validate_labels(
    path: Path,
    *,
    case_ids: set[str],
    cases_sha256: str,
    predictions_sha256: str,
    minimum_labelers: int,
    minimum_overlap_cases: int,
    errors: list[str],
) -> None:
    try:
        payload = _read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"holdout labels are unreadable: {exc}")
        return
    if not isinstance(payload, dict) or payload.get("dataset_role") != "holdout_labels":
        errors.append("holdout labels must have dataset_role=holdout_labels")
        return
    if payload.get("cases_sha256") != cases_sha256 or payload.get("predictions_sha256") != predictions_sha256:
        errors.append("holdout labels must be bound to frozen cases and predictions SHA-256 values")
    labels = payload.get("labels")
    if not isinstance(labels, list):
        errors.append("holdout labels must contain a labels list")
        return
    reviewers: set[str] = set()
    reviewers_by_case: dict[str, set[str]] = {}
    seen_pairs: set[tuple[str, str]] = set()
    for index, label in enumerate(labels):
        if not isinstance(label, dict):
            errors.append(f"holdout label {index} must be an object")
            continue
        unexpected = sorted(set(label) - LABEL_ALLOWED_FIELDS)
        if unexpected:
            errors.append(f"holdout label {index} contains unknown fields: {unexpected}")
        case_id = label.get("id")
        reviewer = label.get("reviewer")
        if not isinstance(case_id, str) or case_id not in case_ids:
            errors.append(f"holdout label {index} references an unknown case")
            continue
        if not isinstance(reviewer, str) or not reviewer.strip():
            errors.append(f"holdout label {index} requires a reviewer pseudonym")
            continue
        pair = (case_id, reviewer)
        if pair in seen_pairs:
            errors.append(f"duplicate holdout label pair: {case_id}/{reviewer}")
        seen_pairs.add(pair)
        reviewers.add(reviewer)
        reviewers_by_case.setdefault(case_id, set()).add(reviewer)
        if label.get("outcome") not in LABEL_OUTCOMES:
            errors.append(f"holdout label {index} has an invalid outcome")
        if label.get("expected_decision") not in MERGE_DECISIONS:
            errors.append(f"holdout label {index} has an invalid expected_decision")
    if len(reviewers) < minimum_labelers:
        errors.append(f"holdout labels require at least {minimum_labelers} independent reviewers")
    overlap = sum(1 for case_reviewers in reviewers_by_case.values() if len(case_reviewers) >= 2)
    if overlap < minimum_overlap_cases:
        errors.append(f"holdout labels require at least {minimum_overlap_cases} double-reviewed cases; found {overlap}")


def validate_manifest(manifest_path: Path = MANIFEST_PATH, repo_root: Path = REPO_ROOT) -> list[str]:
    errors: list[str] = []
    try:
        manifest = _read_json(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"dataset manifest is unreadable: {exc}"]
    if not isinstance(manifest, dict) or manifest.get("version") != 2:
        return ["dataset manifest must be an object with version=2"]

    datasets = manifest.get("datasets")
    if not isinstance(datasets, list):
        errors.append("dataset manifest requires a datasets list")
    else:
        roles: list[object] = []
        paths: set[str] = set()
        for index, dataset in enumerate(datasets):
            if not isinstance(dataset, dict):
                errors.append(f"dataset {index} must be an object")
                continue
            role = dataset.get("role")
            raw_path = dataset.get("path")
            roles.append(role)
            if role not in {"tuning", "regression"}:
                errors.append(f"dataset {index} has invalid role: {role}")
            if not isinstance(raw_path, str) or not raw_path.startswith("eval/"):
                errors.append(f"dataset {index} requires a repository-relative eval path")
                continue
            if raw_path in paths:
                errors.append(f"duplicate dataset path: {raw_path}")
            paths.add(raw_path)
            dataset_path = (repo_root / raw_path).resolve()
            if not dataset_path.exists():
                errors.append(f"dataset path does not exist: {raw_path}")
            elif dataset_path.is_file() and dataset_path.suffix == ".json":
                try:
                    dataset_payload = _read_json(dataset_path)
                except (OSError, json.JSONDecodeError) as exc:
                    errors.append(f"dataset {raw_path} is unreadable: {exc}")
                else:
                    if isinstance(dataset_payload, dict) and dataset_payload.get("dataset_role") != role:
                        errors.append(f"dataset role mismatch for {raw_path}")
        if roles.count("tuning") != 1 or roles.count("regression") != 1:
            errors.append("dataset manifest must declare exactly one tuning and one regression dataset")

    holdout = manifest.get("holdout")
    if not isinstance(holdout, dict):
        return [*errors, "dataset manifest requires a holdout object"]
    status = holdout.get("status")
    if status not in HOLDOUT_PHASES:
        return [*errors, f"holdout status must be one of {HOLDOUT_PHASES}"]
    if holdout.get("protocol_version") != 1:
        errors.append("holdout protocol_version must be 1")
    minimum_cases = holdout.get("minimum_cases")
    minimum_labelers = holdout.get("minimum_independent_labelers")
    minimum_overlap = holdout.get("minimum_overlap_cases")
    if not isinstance(minimum_cases, int) or minimum_cases < 1:
        errors.append("holdout minimum_cases must be a positive integer")
    if not isinstance(minimum_labelers, int) or minimum_labelers < 2:
        errors.append("holdout minimum_independent_labelers must be at least 2")
    if not isinstance(minimum_overlap, int) or minimum_overlap < 1:
        errors.append("holdout minimum_overlap_cases must be a positive integer")
    if errors:
        return errors

    artifact_fields = ("cases_path", "cases_sha256", "predictions_path", "predictions_sha256", "labels_path", "labels_sha256")
    if status == "not_established":
        if any(holdout.get(field) is not None for field in artifact_fields):
            errors.append("not_established holdout cannot reference cases, predictions, labels, or hashes")
        if holdout.get("frozen") is not False:
            errors.append("not_established holdout must set frozen=false")
        if holdout.get("release_claim_blocked") is not True:
            errors.append("not_established holdout must keep release_claim_blocked=true")
        return errors

    if holdout.get("frozen") is not True:
        errors.append("established holdout phases require frozen=true")
    if status != "evaluated" and holdout.get("release_claim_blocked") is not True:
        errors.append("release claims remain blocked until holdout status is evaluated")

    cases_path = _safe_repo_file(repo_root, holdout.get("cases_path"), label="cases_path", errors=errors)
    cases_sha = holdout.get("cases_sha256")
    case_ids: set[str] = set()
    if cases_path is not None:
        _validate_hash(cases_path, cases_sha, label="cases_sha256", errors=errors)
        case_ids = _validate_cases(cases_path, minimum_cases=minimum_cases, errors=errors)

    phase_index = HOLDOUT_PHASES.index(status)
    predictions_sha = holdout.get("predictions_sha256")
    if phase_index >= HOLDOUT_PHASES.index("predictions_frozen"):
        predictions_path = _safe_repo_file(
            repo_root, holdout.get("predictions_path"), label="predictions_path", errors=errors
        )
        if predictions_path is not None:
            _validate_hash(predictions_path, predictions_sha, label="predictions_sha256", errors=errors)
            observed_predictions_sha = _validate_predictions(
                predictions_path, case_ids=case_ids, cases_sha256=str(cases_sha), errors=errors
            )
            if observed_predictions_sha is not None and observed_predictions_sha != predictions_sha:
                errors.append("predictions_sha256 does not match validated prediction content")
    elif any(holdout.get(field) is not None for field in ("predictions_path", "predictions_sha256")):
        errors.append("cases_frozen holdout cannot include predictions before prediction freeze")

    if status == "evaluated":
        labels_path = _safe_repo_file(repo_root, holdout.get("labels_path"), label="labels_path", errors=errors)
        if labels_path is not None:
            _validate_hash(labels_path, holdout.get("labels_sha256"), label="labels_sha256", errors=errors)
            _validate_labels(
                labels_path,
                case_ids=case_ids,
                cases_sha256=str(cases_sha),
                predictions_sha256=str(predictions_sha),
                minimum_labelers=minimum_labelers,
                minimum_overlap_cases=minimum_overlap,
                errors=errors,
            )
    elif any(holdout.get(field) is not None for field in ("labels_path", "labels_sha256")):
        errors.append("holdout labels cannot enter the repository before prediction freeze and evaluation")
    return errors


def validate_change_isolation(changed_paths: set[str]) -> list[str]:
    holdout_changed = any(path.startswith(HOLDOUT_PREFIX) for path in changed_paths)
    analyzer_changed = any(path.startswith(ANALYZER_PREFIXES) for path in changed_paths) or bool(
        changed_paths & ANALYZER_EXACT_PATHS
    )
    if holdout_changed and analyzer_changed:
        return ["holdout artifacts and analyzer/tuning/regression code cannot change in the same commit range"]
    if holdout_changed and "eval/dataset_manifest.json" not in changed_paths:
        return ["holdout artifact changes must update eval/dataset_manifest.json in the same commit range"]
    return []


def changed_paths_from_base(base_sha: str, repo_root: Path = REPO_ROOT) -> set[str]:
    if not re.fullmatch(r"[0-9a-f]{40}", base_sha):
        raise ValueError("AIRISK_EVAL_BASE_SHA must be a lowercase 40-character commit SHA")
    proc = subprocess.run(  # nosec B603
        ["git", "diff", "--name-only", f"{base_sha}...HEAD", "--"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return {line.strip().replace("\\", "/") for line in proc.stdout.splitlines() if line.strip()}


def main() -> int:
    errors = validate_manifest()
    base_sha = os.getenv("AIRISK_EVAL_BASE_SHA", "").strip()
    if base_sha:
        try:
            errors.extend(validate_change_isolation(changed_paths_from_base(base_sha)))
        except (OSError, subprocess.CalledProcessError, ValueError) as exc:
            errors.append(f"unable to inspect eval change isolation: {exc}")
    if errors:
        print("Eval isolation gate failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Eval isolation gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
