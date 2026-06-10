from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
import subprocess  # nosec B404
import sys
import os
from typing import Literal, cast

from ai_risk_manager.pr_scope import normalize_path, source_ref_path

ExecutionStatus = Literal["pass", "setup_fail", "provider_fail", "tool_fail", "artifact_fail", "timeout"]
ProductVerdict = Literal["useful", "mixed", "not_useful", "needs_human_review"]
EvaluationStatus = Literal["passed", "failed", "needs_human_review"]
LabelOutcome = Literal["good_signal", "noisy", "false_positive", "missed_risk"]

_SAFE_CASE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
_SUCCESS_EXIT_CODES = {0, 3}
_REQUIRED_ARTIFACTS = ("pr_summary.json", "merge_triage.json", "findings.json")


@dataclass(frozen=True)
class PublicPRExpectation:
    execution: ExecutionStatus = "pass"
    product: ProductVerdict = "needs_human_review"
    decision: str | None = None
    required_rules: list[str] = field(default_factory=list)
    required_paths: list[str] = field(default_factory=list)
    forbidden_top_rules: list[str] = field(default_factory=list)
    max_top_findings: int | None = None


@dataclass(frozen=True)
class PublicPRLabel:
    outcome: LabelOutcome
    rationale: str
    reviewed_at: str


@dataclass(frozen=True)
class PublicPRCase:
    id: str
    url: str
    stack: str
    reason: str
    expected: PublicPRExpectation
    base: str | None = None
    label: PublicPRLabel | None = None


@dataclass(frozen=True)
class PublicPRBenchmarkOptions:
    case_ids: list[str] = field(default_factory=list)
    limit: int | None = None
    skip_baseline: bool = False
    include_unchanged: bool = False
    enable_llm: bool = False
    provider: str = "auto"
    analysis_engine: str = "deterministic"
    min_confidence: str = "low"
    ci_mode: str = "advisory"
    support_level: str = "auto"
    risk_policy: str = "balanced"
    token_env: str = "GITHUB_TOKEN"
    api_base: str = "https://api.github.com"
    timeout_seconds: int = 900


@dataclass(frozen=True)
class ReviewCommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class PublicPRCaseResult:
    id: str
    url: str
    stack: str
    reason: str
    output_dir: str
    command: list[str]
    returncode: int | None
    execution_status: ExecutionStatus
    expected_execution: ExecutionStatus
    product_verdict: ProductVerdict
    evaluation_status: EvaluationStatus
    decision: str | None = None
    risk_score: int | None = None
    top_finding_count: int = 0
    top_rules: list[str] = field(default_factory=list)
    action_rules: list[str] = field(default_factory=list)
    top_paths: list[str] = field(default_factory=list)
    action_paths: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    stdout_tail: str = ""
    stderr_tail: str = ""


@dataclass
class PublicPRBenchmarkResult:
    generated_at_utc: str
    corpus_path: str
    output_dir: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    needs_human_review_cases: int
    execution_passed_cases: int
    cases: list[PublicPRCaseResult]


@dataclass
class PublicPRCorpusStatus:
    generated_at_utc: str
    corpus_path: str
    total_cases: int
    labeled_cases: int
    pending_cases: int
    outcome_counts: dict[str, int]
    pending_case_ids: list[str]
    issues: list[str]


ReviewCommandRunner = Callable[[list[str], Path, dict[str, str], int], ReviewCommandResult]


def load_public_pr_corpus(path: Path) -> list[PublicPRCase]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc

    raw_cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(raw_cases, list):
        raise ValueError(f"{path}: corpus must be a JSON object with a 'cases' list or a case list")

    cases = [_parse_case(raw_case, index=index, path=path) for index, raw_case in enumerate(raw_cases)]
    seen: set[str] = set()
    for case in cases:
        if case.id in seen:
            raise ValueError(f"{path}: duplicate case id '{case.id}'")
        seen.add(case.id)
    seen_urls: set[str] = set()
    for case in cases:
        if case.url in seen_urls:
            raise ValueError(f"{path}: duplicate case URL '{case.url}'")
        seen_urls.add(case.url)
    return cases


def inspect_public_pr_corpus(path: Path, output_dir: Path) -> PublicPRCorpusStatus:
    cases = load_public_pr_corpus(path)
    pending_case_ids = [case.id for case in cases if case.label is None]
    outcome_counts = {outcome: 0 for outcome in ("good_signal", "noisy", "false_positive", "missed_risk")}
    for case in cases:
        if case.label is not None:
            outcome_counts[case.label.outcome] += 1

    status = PublicPRCorpusStatus(
        generated_at_utc=_utc_now_iso(),
        corpus_path=str(path),
        total_cases=len(cases),
        labeled_cases=len(cases) - len(pending_case_ids),
        pending_cases=len(pending_case_ids),
        outcome_counts=outcome_counts,
        pending_case_ids=pending_case_ids,
        issues=_corpus_labeling_issues(cases),
    )
    write_public_pr_corpus_status(status, output_dir)
    return status


def write_public_pr_corpus_status(result: PublicPRCorpusStatus, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "corpus_status.json").write_text(
        json.dumps(asdict(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "corpus_status.md").write_text(render_public_pr_corpus_status_md(result), encoding="utf-8")


def render_public_pr_corpus_status_md(result: PublicPRCorpusStatus) -> str:
    lines = [
        "# Public PR Corpus Status",
        "",
        f"- Generated: `{result.generated_at_utc}`",
        f"- Corpus: `{result.corpus_path}`",
        f"- Cases: `{result.total_cases}`",
        f"- Labeled: `{result.labeled_cases}`",
        f"- Pending: `{result.pending_cases}`",
        f"- Labeling issues: `{len(result.issues)}`",
        "",
        "## Outcomes",
        "",
    ]
    for outcome, count in result.outcome_counts.items():
        lines.append(f"- `{outcome}`: `{count}`")

    lines.extend(["", "## Pending Queue", ""])
    lines.extend(f"- `{case_id}`" for case_id in result.pending_case_ids)
    if not result.pending_case_ids:
        lines.append("- none")

    lines.extend(["", "## Quality Issues", ""])
    lines.extend(f"- {issue}" for issue in result.issues)
    if not result.issues:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def run_public_pr_benchmark(
    corpus_path: Path,
    output_dir: Path,
    *,
    options: PublicPRBenchmarkOptions | None = None,
    command_runner: ReviewCommandRunner | None = None,
) -> PublicPRBenchmarkResult:
    resolved_options = options or PublicPRBenchmarkOptions()
    cases = _select_cases(load_public_pr_corpus(corpus_path), resolved_options)
    output_dir.mkdir(parents=True, exist_ok=True)
    runner = command_runner or _run_review_command

    results = [
        _run_case(case, output_dir=output_dir, options=resolved_options, command_runner=runner)
        for case in cases
    ]
    benchmark = PublicPRBenchmarkResult(
        generated_at_utc=_utc_now_iso(),
        corpus_path=str(corpus_path),
        output_dir=str(output_dir),
        total_cases=len(results),
        passed_cases=sum(1 for result in results if result.evaluation_status == "passed"),
        failed_cases=sum(1 for result in results if result.evaluation_status == "failed"),
        needs_human_review_cases=sum(1 for result in results if result.evaluation_status == "needs_human_review"),
        execution_passed_cases=sum(1 for result in results if result.execution_status == "pass"),
        cases=results,
    )
    write_public_pr_benchmark_artifacts(benchmark, output_dir)
    return benchmark


def write_public_pr_benchmark_artifacts(result: PublicPRBenchmarkResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "benchmark_summary.json").write_text(
        json.dumps(asdict(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "benchmark_summary.md").write_text(render_public_pr_benchmark_md(result), encoding="utf-8")


def render_public_pr_benchmark_md(result: PublicPRBenchmarkResult) -> str:
    lines = [
        "# Public PR Benchmark Summary",
        "",
        f"- Generated: `{result.generated_at_utc}`",
        f"- Corpus: `{result.corpus_path}`",
        f"- Cases: `{result.total_cases}`",
        f"- Execution passed: `{result.execution_passed_cases}`",
        f"- Evaluation passed: `{result.passed_cases}`",
        f"- Needs human review: `{result.needs_human_review_cases}`",
        f"- Failed: `{result.failed_cases}`",
        "",
        "| Case | Stack | Execution | Product | Evaluation | Decision | Risk | Top Rules | Errors |",
        "|---|---|---|---|---|---|---:|---|---|",
    ]
    for case in result.cases:
        top_rules = ", ".join(case.top_rules[:5]) if case.top_rules else "none"
        errors = "<br>".join(case.errors[:3]) if case.errors else "none"
        lines.append(
            "| "
            f"`{case.id}` | "
            f"`{case.stack}` | "
            f"`{case.execution_status}` | "
            f"`{case.product_verdict}` | "
            f"`{case.evaluation_status}` | "
            f"`{case.decision or 'unknown'}` | "
            f"`{case.risk_score if case.risk_score is not None else 'n/a'}` | "
            f"{top_rules} | "
            f"{errors} |"
        )
    lines.append("")
    return "\n".join(lines)


def _run_case(
    case: PublicPRCase,
    *,
    output_dir: Path,
    options: PublicPRBenchmarkOptions,
    command_runner: ReviewCommandRunner,
) -> PublicPRCaseResult:
    case_output_dir = output_dir / case.id
    command = _build_review_command(case, case_output_dir, options)
    try:
        proc = command_runner(command, Path.cwd(), _benchmark_env(), options.timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        result = _base_result(
            case,
            output_dir=case_output_dir,
            command=command,
            returncode=None,
            execution_status="timeout",
            stdout=str(exc.stdout or ""),
            stderr=str(exc.stderr or ""),
        )
        _evaluate_case_result(case, result)
        return result

    execution_status = _resolve_execution_status(proc.returncode, case_output_dir)
    result = _base_result(
        case,
        output_dir=case_output_dir,
        command=command,
        returncode=proc.returncode,
        execution_status=execution_status,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )
    if execution_status == "pass":
        _populate_observed_artifacts(result, case_output_dir)
    _evaluate_case_result(case, result)
    return result


def _build_review_command(case: PublicPRCase, output_dir: Path, options: PublicPRBenchmarkOptions) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "ai_risk_manager.cli",
        "review-pr",
        case.url,
        "--output-dir",
        str(output_dir),
        "--format",
        "both",
        "--provider",
        options.provider,
        "--analysis-engine",
        options.analysis_engine,
        "--min-confidence",
        options.min_confidence,
        "--ci-mode",
        options.ci_mode,
        "--support-level",
        options.support_level,
        "--risk-policy",
        options.risk_policy,
        "--token-env",
        options.token_env,
        "--api-base",
        options.api_base,
    ]
    if case.base:
        command.extend(["--base", case.base])
    if options.skip_baseline:
        command.append("--skip-baseline")
    if options.include_unchanged:
        command.append("--include-unchanged")
    if options.enable_llm:
        command.append("--enable-llm")
    return command


def _run_review_command(cmd: list[str], cwd: Path, env: dict[str, str], timeout_seconds: int) -> ReviewCommandResult:
    proc = subprocess.run(  # nosec B603
        cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return ReviewCommandResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def _benchmark_env() -> dict[str, str]:
    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[1])
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src_path if not existing else f"{src_path}{os.pathsep}{existing}"
    return env


def _resolve_execution_status(returncode: int, output_dir: Path) -> ExecutionStatus:
    if returncode in _SUCCESS_EXIT_CODES:
        missing = [name for name in _REQUIRED_ARTIFACTS if not (output_dir / name).is_file()]
        return "artifact_fail" if missing else "pass"
    if returncode == 2:
        return "setup_fail"
    if returncode == 1:
        return "provider_fail"
    return "tool_fail"


def _populate_observed_artifacts(result: PublicPRCaseResult, output_dir: Path) -> None:
    try:
        pr_summary = _read_json_object(output_dir / "pr_summary.json")
        merge_triage = _read_json_object(output_dir / "merge_triage.json")
    except ValueError as exc:
        result.execution_status = "artifact_fail"
        result.errors.append(str(exc))
        return

    result.decision = _optional_str(pr_summary.get("decision"))
    risk_score = pr_summary.get("risk_score")
    if isinstance(risk_score, int):
        result.risk_score = risk_score

    top_findings = _object_list(pr_summary.get("top_findings"))
    top_actions = _object_list(pr_summary.get("top_actions"))
    merge_actions = _object_list(merge_triage.get("actions"))
    result.top_finding_count = len(top_findings)
    result.top_rules = _unique_strings(_extract_field(top_findings, "rule_id"))
    result.action_rules = _unique_strings(
        [*_extract_field(top_actions, "rule_id"), *_extract_field(merge_actions, "rule_id")]
    )
    result.top_paths = _unique_strings(_normalize_source_refs(_extract_field(top_findings, "source_ref")))
    result.action_paths = _unique_strings(
        _normalize_source_refs([*_extract_field(top_actions, "source_ref"), *_extract_field(merge_actions, "source_ref")])
    )


def _evaluate_case_result(case: PublicPRCase, result: PublicPRCaseResult) -> None:
    expected = case.expected
    if result.execution_status != expected.execution:
        result.errors.append(f"expected execution `{expected.execution}`, got `{result.execution_status}`")

    if result.execution_status == "pass":
        if expected.decision and result.decision != expected.decision:
            result.errors.append(f"expected decision `{expected.decision}`, got `{result.decision or 'unknown'}`")

        surface_rules = set(result.top_rules) | set(result.action_rules)
        missing_rules = sorted(set(expected.required_rules) - surface_rules)
        if missing_rules:
            result.errors.append(f"missing required surfaced rule(s): {missing_rules}")

        forbidden_rules = sorted(set(expected.forbidden_top_rules) & surface_rules)
        if forbidden_rules:
            result.errors.append(f"found forbidden surfaced rule(s): {forbidden_rules}")

        surface_paths = set(result.top_paths) | set(result.action_paths)
        missing_paths = sorted(path for path in expected.required_paths if not _path_was_surfaced(path, surface_paths))
        if missing_paths:
            result.errors.append(f"missing required surfaced path(s): {missing_paths}")

        if expected.max_top_findings is not None and result.top_finding_count > expected.max_top_findings:
            result.errors.append(
                f"expected at most {expected.max_top_findings} top finding(s), got {result.top_finding_count}"
            )

    if result.errors:
        result.evaluation_status = "failed"
    elif expected.product == "needs_human_review":
        result.evaluation_status = "needs_human_review"
    else:
        result.evaluation_status = "passed"


def _base_result(
    case: PublicPRCase,
    *,
    output_dir: Path,
    command: list[str],
    returncode: int | None,
    execution_status: ExecutionStatus,
    stdout: str,
    stderr: str,
) -> PublicPRCaseResult:
    return PublicPRCaseResult(
        id=case.id,
        url=case.url,
        stack=case.stack,
        reason=case.reason,
        output_dir=str(output_dir),
        command=command,
        returncode=returncode,
        execution_status=execution_status,
        expected_execution=case.expected.execution,
        product_verdict=case.expected.product,
        evaluation_status="failed",
        stdout_tail=_tail(stdout),
        stderr_tail=_tail(stderr),
    )


def _select_cases(cases: list[PublicPRCase], options: PublicPRBenchmarkOptions) -> list[PublicPRCase]:
    selected = cases
    if options.case_ids:
        wanted = set(options.case_ids)
        selected = [case for case in selected if case.id in wanted]
        missing = sorted(wanted - {case.id for case in selected})
        if missing:
            raise ValueError(f"unknown public PR benchmark case id(s): {missing}")
    if options.limit is not None:
        if options.limit <= 0:
            raise ValueError("benchmark --limit must be a positive integer")
        selected = selected[: options.limit]
    return selected


def _parse_case(raw_case: object, *, index: int, path: Path) -> PublicPRCase:
    if not isinstance(raw_case, dict):
        raise ValueError(f"{path}: case #{index + 1} must be an object")

    case_id = _required_str(raw_case, "id", path=path, index=index)
    if not _SAFE_CASE_ID.match(case_id):
        raise ValueError(f"{path}: case '{case_id}' id may only contain letters, numbers, '.', '_' and '-'")

    expected_payload = raw_case.get("expected", {})
    if expected_payload is None:
        expected_payload = {}
    if not isinstance(expected_payload, dict):
        raise ValueError(f"{path}: case '{case_id}' expected must be an object")

    return PublicPRCase(
        id=case_id,
        url=_required_str(raw_case, "url", path=path, index=index),
        stack=_optional_str(raw_case.get("stack")) or "unknown",
        reason=_optional_str(raw_case.get("reason")) or "",
        base=_optional_str(raw_case.get("base")),
        label=_parse_label(raw_case.get("label"), case_id=case_id, path=path),
        expected=PublicPRExpectation(
            execution=cast(
                ExecutionStatus,
                _parse_literal(
                    expected_payload.get("execution", "pass"),
                    {"pass", "setup_fail", "provider_fail", "tool_fail", "artifact_fail", "timeout"},
                    field_name=f"{case_id}.expected.execution",
                    path=path,
                ),
            ),
            product=cast(
                ProductVerdict,
                _parse_literal(
                    expected_payload.get("product", "needs_human_review"),
                    {"useful", "mixed", "not_useful", "needs_human_review"},
                    field_name=f"{case_id}.expected.product",
                    path=path,
                ),
            ),
            decision=_optional_str(expected_payload.get("decision")),
            required_rules=_str_list(expected_payload.get("required_rules"), field_name=f"{case_id}.expected.required_rules", path=path),
            required_paths=_str_list(expected_payload.get("required_paths"), field_name=f"{case_id}.expected.required_paths", path=path),
            forbidden_top_rules=_str_list(
                expected_payload.get("forbidden_top_rules"),
                field_name=f"{case_id}.expected.forbidden_top_rules",
                path=path,
            ),
            max_top_findings=_optional_int(
                expected_payload.get("max_top_findings"),
                field_name=f"{case_id}.expected.max_top_findings",
                path=path,
            ),
        ),
    )


def _parse_label(value: object, *, case_id: str, path: Path) -> PublicPRLabel | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{path}: case '{case_id}' label must be an object")

    rationale = _optional_str(value.get("rationale"))
    if rationale is None:
        raise ValueError(f"{path}: {case_id}.label.rationale must be a non-empty string")
    reviewed_at = _optional_str(value.get("reviewed_at"))
    if reviewed_at is None:
        raise ValueError(f"{path}: {case_id}.label.reviewed_at must be an ISO date")
    try:
        date.fromisoformat(reviewed_at)
    except ValueError as exc:
        raise ValueError(f"{path}: {case_id}.label.reviewed_at must be an ISO date") from exc

    return PublicPRLabel(
        outcome=cast(
            LabelOutcome,
            _parse_literal(
                value.get("outcome"),
                {"good_signal", "noisy", "false_positive", "missed_risk"},
                field_name=f"{case_id}.label.outcome",
                path=path,
            ),
        ),
        rationale=rationale,
        reviewed_at=reviewed_at,
    )


def _corpus_labeling_issues(cases: list[PublicPRCase]) -> list[str]:
    issues: list[str] = []
    expected_products: dict[LabelOutcome, set[ProductVerdict]] = {
        "good_signal": {"useful"},
        "noisy": {"mixed"},
        "false_positive": {"not_useful"},
        "missed_risk": {"mixed", "not_useful"},
    }
    for case in cases:
        if case.label is None:
            if case.expected.product != "needs_human_review":
                issues.append(
                    f"`{case.id}` has product `{case.expected.product}` but no label metadata"
                )
            continue
        if case.expected.product == "needs_human_review":
            issues.append(f"`{case.id}` has label metadata but product is still `needs_human_review`")
            continue
        allowed_products = expected_products[case.label.outcome]
        if case.expected.product not in allowed_products:
            allowed = ", ".join(f"`{product}`" for product in sorted(allowed_products))
            issues.append(
                f"`{case.id}` outcome `{case.label.outcome}` requires product {allowed}, "
                f"got `{case.expected.product}`"
            )
    return issues


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: cannot read JSON artifact: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON artifact must be an object")
    return payload


def _required_str(payload: dict[str, object], key: str, *, path: Path, index: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: case #{index + 1} field '{key}' must be a non-empty string")
    return value.strip()


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _optional_int(value: object, *, field_name: str, path: Path) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and value >= 0:
        return value
    raise ValueError(f"{path}: {field_name} must be a non-negative integer")


def _parse_literal(value: object, allowed: set[str], *, field_name: str, path: Path) -> str:
    if isinstance(value, str) and value in allowed:
        return value
    raise ValueError(f"{path}: {field_name} must be one of {sorted(allowed)}")


def _str_list(value: object, *, field_name: str, path: Path) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{path}: {field_name} must be a list of non-empty strings")
    return [item.strip() for item in value]


def _object_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _extract_field(rows: list[dict[str, object]], field_name: str) -> list[str]:
    return [value for row in rows if isinstance(value := row.get(field_name), str) and value.strip()]


def _normalize_source_refs(refs: list[str]) -> list[str]:
    return [normalize_path(source_ref_path(ref)) for ref in refs]


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        unique.append(value)
        seen.add(value)
    return unique


def _path_was_surfaced(expected_path: str, surfaced_paths: set[str]) -> bool:
    normalized_expected = normalize_path(source_ref_path(expected_path))
    return normalized_expected in surfaced_paths


def _tail(text: str, *, max_chars: int = 4000) -> str:
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
