from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_risk_manager.artifact_io import write_text_atomic, write_text_new_atomic  # noqa: E402


CASE_FIELDS = {"id", "url", "head_sha", "stack", "selected_at"}
SELECTION_POLICY_FIELDS = {
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
EXECUTIONS = {"pass", "setup_fail", "provider_fail", "tool_fail", "artifact_fail", "timeout"}
DECISIONS = {"ready", "review_required", "block_recommended"}
SHA40 = re.compile(r"[0-9a-f]{40}")
SHA64 = re.compile(r"[0-9a-f]{64}")
PR_URL = re.compile(r"https://github\.com/[^/]+/[^/]+/pull/[1-9][0-9]*")


class HoldoutWorkflowError(ValueError):
    pass


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HoldoutWorkflowError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise HoldoutWorkflowError(f"expected a JSON object in {path}")
    return payload


def _write_new_json(path: Path, payload: object) -> None:
    try:
        write_text_new_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    except FileExistsError as exc:
        raise HoldoutWorkflowError(f"refusing to overwrite frozen artifact: {path}") from exc
    except OSError as exc:
        raise HoldoutWorkflowError(f"cannot create frozen artifact {path}: {exc}") from exc


def _write_json(path: Path, payload: object) -> None:
    write_text_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _relative_holdout_path(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise HoldoutWorkflowError("holdout artifacts must be inside the repository") from exc
    if not relative.startswith("eval/holdout/"):
        raise HoldoutWorkflowError("holdout artifacts must be under eval/holdout/")
    return relative


def _manifest_holdout(manifest: dict[str, Any], expected_status: str) -> dict[str, Any]:
    if manifest.get("version") != 2 or not isinstance(manifest.get("holdout"), dict):
        raise HoldoutWorkflowError("dataset manifest must use version 2 and contain holdout state")
    holdout = manifest["holdout"]
    if holdout.get("status") != expected_status:
        raise HoldoutWorkflowError(
            f"holdout must be in {expected_status} state; found {holdout.get('status')!r}"
        )
    return holdout


def _validate_cases(cases: object, minimum_cases: int) -> list[dict[str, str]]:
    if not isinstance(cases, list):
        raise HoldoutWorkflowError("candidate packet must contain a cases list")
    if len(cases) < minimum_cases:
        raise HoldoutWorkflowError(f"holdout requires at least {minimum_cases} cases; found {len(cases)}")

    normalized: list[dict[str, str]] = []
    ids: set[str] = set()
    urls: set[str] = set()
    shas: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or set(case) != CASE_FIELDS:
            raise HoldoutWorkflowError(f"case {index} must contain exactly {sorted(CASE_FIELDS)}")
        if not all(isinstance(case[field], str) and case[field].strip() for field in CASE_FIELDS):
            raise HoldoutWorkflowError(f"case {index} fields must be non-empty strings")
        if not PR_URL.fullmatch(case["url"]):
            raise HoldoutWorkflowError(f"case {index} has an invalid public GitHub PR URL")
        if not SHA40.fullmatch(case["head_sha"]):
            raise HoldoutWorkflowError(f"case {index} has an invalid head SHA")
        if case["id"] in ids or case["url"] in urls or case["head_sha"] in shas:
            raise HoldoutWorkflowError(f"case {index} duplicates an id, URL, or head SHA")
        ids.add(case["id"])
        urls.add(case["url"])
        shas.add(case["head_sha"])
        normalized.append({field: case[field] for field in ("id", "url", "head_sha", "stack", "selected_at")})
    return normalized


def _validate_selection_policy(policy: object, regression_path: Path, cases: list[dict[str, str]]) -> dict[str, Any]:
    if not isinstance(policy, dict) or set(policy) != SELECTION_POLICY_FIELDS:
        raise HoldoutWorkflowError(f"selection_policy must contain exactly {sorted(SELECTION_POLICY_FIELDS)}")
    repositories = policy.get("repositories")
    quota = policy.get("per_repository")
    if (
        not isinstance(repositories, list)
        or not repositories
        or not all(isinstance(repo, str) and re.fullmatch(r"[^/]+/[^/]+", repo) for repo in repositories)
        or len(repositories) != len(set(repositories))
    ):
        raise HoldoutWorkflowError("selection_policy repositories must be unique owner/repository strings")
    if not isinstance(quota, int) or isinstance(quota, bool) or quota < 1:
        raise HoldoutWorkflowError("selection_policy per_repository must be a positive integer")
    if len(cases) != len(repositories) * quota:
        raise HoldoutWorkflowError("case count must match the repository quota in selection_policy")
    counts = {repository: 0 for repository in repositories}
    for case in cases:
        match = re.match(r"https://github\.com/([^/]+/[^/]+)/pull/", case["url"])
        repository = match.group(1) if match else ""
        if repository not in counts:
            raise HoldoutWorkflowError(f"case {case['id']} is outside selection_policy repositories")
        counts[repository] += 1
        if case["selected_at"] != policy.get("selected_at"):
            raise HoldoutWorkflowError("case selected_at values must match selection_policy selected_at")
    if any(count != quota for count in counts.values()):
        raise HoldoutWorkflowError("each selection_policy repository must satisfy per_repository quota")
    if policy.get("states") != ["MERGED"]:
        raise HoldoutWorkflowError("selection_policy states must be [MERGED]")
    for field in ("changed_files", "diff_size"):
        bounds = policy.get(field)
        if (
            not isinstance(bounds, list)
            or len(bounds) != 2
            or not all(isinstance(value, int) and not isinstance(value, bool) for value in bounds)
            or bounds[0] < 0
            or bounds[0] > bounds[1]
        ):
            raise HoldoutWorkflowError(f"selection_policy {field} must be ordered non-negative integer bounds")
    if policy.get("ordering") != "most_recently_updated_eligible":
        raise HoldoutWorkflowError("selection_policy ordering must be most_recently_updated_eligible")
    if policy.get("excluded_dataset") != "eval/public_prs.json":
        raise HoldoutWorkflowError("selection_policy excluded_dataset must be eval/public_prs.json")
    expected_regression_hash = policy.get("excluded_dataset_sha256")
    if not isinstance(expected_regression_hash, str) or not SHA64.fullmatch(expected_regression_hash):
        raise HoldoutWorkflowError("selection_policy excluded_dataset_sha256 must be a SHA-256")
    if _sha256(regression_path) != expected_regression_hash:
        raise HoldoutWorkflowError("selection_policy excluded dataset hash does not match the regression corpus")
    selected_at = policy.get("selected_at")
    if not isinstance(selected_at, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", selected_at):
        raise HoldoutWorkflowError("selection_policy selected_at must be an ISO date")
    return policy


def freeze_cases(
    candidate_path: Path,
    output_path: Path,
    manifest_path: Path,
    regression_path: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> str:
    manifest = _read_object(manifest_path)
    holdout = _manifest_holdout(manifest, "not_established")
    minimum_cases = holdout.get("minimum_cases")
    if not isinstance(minimum_cases, int) or minimum_cases < 1:
        raise HoldoutWorkflowError("manifest minimum_cases must be a positive integer")

    candidates = _read_object(candidate_path)
    if candidates.get("dataset_role") != "holdout_candidates":
        raise HoldoutWorkflowError("candidate packet must have dataset_role=holdout_candidates")
    cases = _validate_cases(candidates.get("cases"), minimum_cases)
    selection_policy = _validate_selection_policy(candidates.get("selection_policy"), regression_path, cases)

    regression = _read_object(regression_path)
    regression_cases = regression.get("cases")
    if not isinstance(regression_cases, list):
        raise HoldoutWorkflowError("regression corpus must contain a cases list")
    known_urls = {case.get("url") for case in regression_cases if isinstance(case, dict)}
    known_shas = {case.get("head_sha") for case in regression_cases if isinstance(case, dict)}
    reused = [case["id"] for case in cases if case["url"] in known_urls or case["head_sha"] in known_shas]
    if reused:
        raise HoldoutWorkflowError(f"holdout reuses regression cases: {', '.join(reused)}")

    relative_output = _relative_holdout_path(output_path, repo_root)
    _write_new_json(
        output_path,
        {"version": 1, "dataset_role": "holdout", "selection_policy": selection_policy, "cases": cases},
    )
    cases_hash = _sha256(output_path)
    holdout.update(
        {
            "status": "cases_frozen",
            "frozen": True,
            "cases_path": relative_output,
            "cases_sha256": cases_hash,
            "release_claim_blocked": True,
        }
    )
    try:
        _write_json(manifest_path, manifest)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    return cases_hash


def _case_prediction(case_id: str, case_dir: Path) -> dict[str, Any]:
    execution_path = case_dir / "execution.json"
    if execution_path.is_file():
        execution_payload = _read_object(execution_path)
        execution = execution_payload.get("execution")
        if execution not in EXECUTIONS - {"pass"}:
            raise HoldoutWorkflowError(f"{case_id}: execution.json must contain a non-pass failure status")
        return {
            "id": case_id,
            "execution": execution,
            "decision": None,
            "top_rules": [],
            "finding_count": 0,
            "artifact_hash": _artifact_hash([execution_path]),
        }

    required = [case_dir / name for name in ("pr_summary.json", "merge_triage.json", "findings.json")]
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        raise HoldoutWorkflowError(f"{case_id}: missing result artifacts: {', '.join(missing)}")
    summary = _read_object(required[0])
    triage = _read_object(required[1])
    findings_payload = _read_object(required[2])
    decision = triage.get("decision")
    if decision not in DECISIONS or summary.get("decision") != decision:
        raise HoldoutWorkflowError(f"{case_id}: summary and triage must contain the same valid decision")
    findings = findings_payload.get("findings")
    if not isinstance(findings, list) or not all(isinstance(item, dict) for item in findings):
        raise HoldoutWorkflowError(f"{case_id}: findings.json must contain a findings object list")
    top_findings = summary.get("top_findings")
    if not isinstance(top_findings, list) or not all(isinstance(item, dict) for item in top_findings):
        raise HoldoutWorkflowError(f"{case_id}: pr_summary.json must contain a top_findings object list")
    top_rules = list(dict.fromkeys(item.get("rule_id") for item in top_findings if isinstance(item.get("rule_id"), str)))
    return {
        "id": case_id,
        "execution": "pass",
        "decision": decision,
        "top_rules": top_rules,
        "finding_count": len(findings),
        "artifact_hash": _artifact_hash(required),
    }


def freeze_predictions(
    results_dir: Path,
    output_path: Path,
    manifest_path: Path,
    source_commit: str,
    *,
    repo_root: Path = REPO_ROOT,
) -> str:
    if not SHA40.fullmatch(source_commit):
        raise HoldoutWorkflowError("source commit must be a lowercase 40-character SHA")
    manifest = _read_object(manifest_path)
    holdout = _manifest_holdout(manifest, "cases_frozen")
    cases_path_raw = holdout.get("cases_path")
    cases_hash = holdout.get("cases_sha256")
    if not isinstance(cases_path_raw, str) or not isinstance(cases_hash, str) or not SHA64.fullmatch(cases_hash):
        raise HoldoutWorkflowError("manifest does not reference valid frozen cases")
    cases_path = repo_root / cases_path_raw
    if not cases_path.is_file() or _sha256(cases_path) != cases_hash:
        raise HoldoutWorkflowError("frozen cases file is missing or its hash has drifted")
    cases = _read_object(cases_path).get("cases")
    if not isinstance(cases, list):
        raise HoldoutWorkflowError("frozen cases file must contain a cases list")
    case_ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(case_ids) != len(cases) or not all(isinstance(case_id, str) for case_id in case_ids):
        raise HoldoutWorkflowError("frozen cases contain invalid IDs")

    predictions = [_case_prediction(case_id, results_dir / case_id) for case_id in case_ids]
    relative_output = _relative_holdout_path(output_path, repo_root)
    _write_new_json(
        output_path,
        {
            "version": 1,
            "dataset_role": "holdout_predictions",
            "cases_sha256": cases_hash,
            "generated_from_commit": source_commit,
            "predictions": predictions,
        },
    )
    predictions_hash = _sha256(output_path)
    holdout.update(
        {
            "status": "predictions_frozen",
            "predictions_path": relative_output,
            "predictions_sha256": predictions_hash,
            "release_claim_blocked": True,
        }
    )
    try:
        _write_json(manifest_path, manifest)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    return predictions_hash


def create_label_template(manifest_path: Path, output_path: Path, reviewer: str, *, repo_root: Path = REPO_ROOT) -> None:
    if not reviewer.strip():
        raise HoldoutWorkflowError("reviewer pseudonym must be non-empty")
    manifest = _read_object(manifest_path)
    holdout = _manifest_holdout(manifest, "predictions_frozen")
    cases_path_raw = holdout.get("cases_path")
    cases_hash = holdout.get("cases_sha256")
    predictions_hash = holdout.get("predictions_sha256")
    if not isinstance(cases_path_raw, str) or not isinstance(cases_hash, str) or not isinstance(predictions_hash, str):
        raise HoldoutWorkflowError("manifest does not reference frozen cases and predictions")
    cases = _read_object(repo_root / cases_path_raw).get("cases")
    if not isinstance(cases, list):
        raise HoldoutWorkflowError("frozen cases file must contain a cases list")
    labels = [
        {
            "id": case["id"],
            "reviewer": reviewer,
            "outcome": None,
            "expected_decision": None,
            "rationale": None,
            "reviewed_at": None,
        }
        for case in cases
        if isinstance(case, dict) and isinstance(case.get("id"), str)
    ]
    _write_new_json(
        output_path,
        {
            "version": 1,
            "dataset_role": "holdout_label_template",
            "cases_sha256": cases_hash,
            "predictions_sha256": predictions_hash,
            "labels": labels,
        },
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare frozen holdout artifacts without exposing labels to analysis.")
    parser.add_argument("--manifest", type=Path, default=REPO_ROOT / "eval" / "dataset_manifest.json")
    subparsers = parser.add_subparsers(dest="command", required=True)

    cases = subparsers.add_parser("freeze-cases")
    cases.add_argument("--input", type=Path, required=True)
    cases.add_argument("--output", type=Path, default=REPO_ROOT / "eval" / "holdout" / "cases.json")
    cases.add_argument("--regression", type=Path, default=REPO_ROOT / "eval" / "public_prs.json")

    predictions = subparsers.add_parser("freeze-predictions")
    predictions.add_argument("--results-dir", type=Path, required=True)
    predictions.add_argument("--output", type=Path, default=REPO_ROOT / "eval" / "holdout" / "predictions.json")
    predictions.add_argument("--source-commit", required=True)

    labels = subparsers.add_parser("create-label-template")
    labels.add_argument("--output", type=Path, required=True)
    labels.add_argument("--reviewer", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo_root = args.manifest.resolve().parents[1]
    try:
        if args.command == "freeze-cases":
            digest = freeze_cases(args.input, args.output, args.manifest, args.regression, repo_root=repo_root)
        elif args.command == "freeze-predictions":
            digest = freeze_predictions(
                args.results_dir, args.output, args.manifest, args.source_commit, repo_root=repo_root
            )
        else:
            create_label_template(args.manifest, args.output, args.reviewer, repo_root=repo_root)
            digest = _sha256(args.output)
    except HoldoutWorkflowError as exc:
        print(f"Holdout workflow failed: {exc}", file=sys.stderr)
        return 2
    print(f"Holdout artifact created: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
