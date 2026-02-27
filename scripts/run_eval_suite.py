from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / "eval" / "results"
HISTORY_ROOT = REPO_ROOT / "eval" / ".history"
TRUST_THRESHOLDS_PATH = REPO_ROOT / "eval" / "trust_thresholds.json"
DEFAULT_HISTORY_PATH = HISTORY_ROOT / "trust_gate_history.jsonl"
DEFAULT_TREND_WINDOW = 12
PERCENT_METRICS = {
    "avg_precision_proxy",
    "avg_recall_proxy",
    "avg_actionability_proxy",
    "avg_evidence_completeness",
    "avg_verification_pass_rate",
    "avg_fallback_rate",
}
DEFAULT_TRUST_THRESHOLDS: dict[str, float] = {
    "min_avg_precision_proxy": 0.75,
    "min_avg_recall_proxy": 0.75,
    "min_avg_actionability_proxy": 0.40,
    "min_avg_evidence_completeness": 0.95,
    "min_avg_verification_pass_rate": 0.95,
    "max_avg_triage_time_proxy_min": 10.0,
    "max_flaky_cases": 0.0,
    "max_avg_fallback_rate": 0.15,
}


@dataclass
class EvalCase:
    name: str
    repo_rel: str
    required_rules: set[str]
    forbidden_rules: set[str]


CASES = [
    EvalCase(
        name="milestone2_fastapi",
        repo_rel="eval/repos/milestone2_fastapi",
        required_rules={"critical_path_no_tests", "missing_transition_handler"},
        forbidden_rules=set(),
    ),
    EvalCase(
        name="milestone5_balanced",
        repo_rel="eval/repos/milestone5_balanced",
        required_rules=set(),
        forbidden_rules={"critical_path_no_tests", "missing_transition_handler"},
    ),
    EvalCase(
        name="milestone5_missing_handler",
        repo_rel="eval/repos/milestone5_missing_handler",
        required_rules={"missing_transition_handler"},
        forbidden_rules={"critical_path_no_tests"},
    ),
]


def _safe_mean(values: list[float]) -> float:
    return mean(values) if values else 0.0


def _parse_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _parse_positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_history_path() -> Path:
    raw = os.getenv("AIRISK_EVAL_HISTORY_PATH")
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_HISTORY_PATH


def load_trend_history(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def write_trend_history(path: Path, history: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=False) for row in history]
    text = "\n".join(lines)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")


def _build_trend_snapshot(aggregates: dict[str, float], gate_payload: dict[str, object]) -> dict:
    return {
        "generated_at_utc": _utc_now_iso(),
        "run_id": os.getenv("GITHUB_RUN_ID", "local"),
        "git_sha": os.getenv("GITHUB_SHA", "local"),
        "git_ref": os.getenv("GITHUB_REF_NAME") or os.getenv("GITHUB_REF", "local"),
        "gate_status": gate_payload.get("status", "unknown"),
        "aggregates": {key: float(value) for key, value in aggregates.items()},
    }


def _build_trend_payload(history: list[dict]) -> dict:
    latest = history[-1] if history else None
    delta_vs_previous: dict[str, float] = {}
    if len(history) >= 2:
        prev = history[-2].get("aggregates", {})
        curr = history[-1].get("aggregates", {})
        if isinstance(prev, dict) and isinstance(curr, dict):
            for metric_name in curr:
                prev_value = prev.get(metric_name)
                curr_value = curr.get(metric_name)
                if isinstance(prev_value, (int, float)) and isinstance(curr_value, (int, float)):
                    delta_vs_previous[metric_name] = float(curr_value) - float(prev_value)
    return {
        "window_size": len(history),
        "latest": latest,
        "delta_vs_previous": delta_vs_previous,
        "history": history,
    }


def _render_delta(value: float, metric_name: str) -> str:
    if metric_name in PERCENT_METRICS:
        return f"{value * 100:+.2f} pp"
    if metric_name == "avg_triage_time_proxy_min":
        return f"{value:+.2f} min"
    if metric_name == "flaky_cases":
        return f"{value:+.0f}"
    return f"{value:+.4f}"


def render_trend_md(history: list[dict], delta_vs_previous: dict[str, float]) -> str:
    lines = [
        "# Eval Trust Trend",
        "",
        f"- Window size: `{len(history)}`",
        "",
        "| Run (UTC) | Gate | Precision | Recall | Actionability | Evidence | Verification | Fallback | Triage | Flaky |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in reversed(history):
        aggregates = row.get("aggregates", {})
        if not isinstance(aggregates, dict):
            continue
        lines.append(
            "| "
            f"{row.get('generated_at_utc', 'unknown')} | "
            f"{row.get('gate_status', 'unknown')} | "
            f"{float(aggregates.get('avg_precision_proxy', 0.0)):.2%} | "
            f"{float(aggregates.get('avg_recall_proxy', 0.0)):.2%} | "
            f"{float(aggregates.get('avg_actionability_proxy', 0.0)):.2%} | "
            f"{float(aggregates.get('avg_evidence_completeness', 0.0)):.2%} | "
            f"{float(aggregates.get('avg_verification_pass_rate', 0.0)):.2%} | "
            f"{float(aggregates.get('avg_fallback_rate', 0.0)):.2%} | "
            f"{float(aggregates.get('avg_triage_time_proxy_min', 0.0)):.1f} min | "
            f"{int(float(aggregates.get('flaky_cases', 0.0)))} |"
        )

    if delta_vs_previous:
        lines.extend(["", "## Delta vs Previous Run", ""])
        for metric_name in sorted(delta_vs_previous):
            lines.append(f"- {metric_name}: `{_render_delta(delta_vs_previous[metric_name], metric_name)}`")
    lines.append("")
    return "\n".join(lines)


def write_trend_artifacts(
    *,
    aggregates: dict[str, float],
    gate_payload: dict[str, object],
    output_root: Path = OUTPUT_ROOT,
    history_path: Path | None = None,
    trend_window: int | None = None,
) -> None:
    resolved_history_path = history_path or resolve_history_path()
    resolved_window = trend_window or _parse_positive_int_env("AIRISK_EVAL_TREND_WINDOW", DEFAULT_TREND_WINDOW)
    history = load_trend_history(resolved_history_path)
    history.append(_build_trend_snapshot(aggregates, gate_payload))
    history = history[-resolved_window:]
    write_trend_history(resolved_history_path, history)
    write_trend_history(output_root / "trust_history.jsonl", history)

    trend_payload = _build_trend_payload(history)
    (output_root / "trust_trend.json").write_text(json.dumps(trend_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_root / "trust_trend.md").write_text(
        render_trend_md(history, trend_payload["delta_vs_previous"]),
        encoding="utf-8",
    )


def load_trust_thresholds(path: Path = TRUST_THRESHOLDS_PATH) -> dict[str, float]:
    thresholds = dict(DEFAULT_TRUST_THRESHOLDS)
    if not path.is_file():
        return thresholds
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return thresholds
    if not isinstance(payload, dict):
        return thresholds

    for key, value in payload.items():
        if key in thresholds and isinstance(value, (int, float)):
            thresholds[key] = float(value)
    return thresholds


def run_case(case: EvalCase) -> dict:
    repo_path = REPO_ROOT / case.repo_rel
    out_dir = OUTPUT_ROOT / case.name
    out_dir.mkdir(parents=True, exist_ok=True)

    result: dict = {
        "case": case.name,
        "repo": case.repo_rel,
        "exit_code": 0,
        "required_rules": sorted(case.required_rules),
        "forbidden_rules": sorted(case.forbidden_rules),
        "found_rules": [],
        "runs": [],
        "required_missed_count": 0,
        "forbidden_hit_count": 0,
        "precision_proxy": 1.0,
        "recall_proxy": 1.0,
        "actionability_proxy": 1.0,
        "evidence_completeness": 1.0,
        "verification_pass_rate": 1.0,
        "fallback_rate": 0.0,
        "triage_time_proxy_min": 0.0,
        "flaky": False,
        "status": "failed",
        "errors": [],
    }

    try:
        run_count = int(os.getenv("AIRISK_EVAL_FLAKY_RUNS", "2"))
    except ValueError:
        run_count = 2
    if run_count < 1:
        run_count = 1

    rules_per_run: list[set[str]] = []
    metrics_per_run: list[dict] = []
    for run_idx in range(run_count):
        cmd = [
            sys.executable,
            "-m",
            "ai_risk_manager.cli",
            "analyze",
            str(repo_path),
            "--mode",
            "full",
            "--no-llm",
            "--output-dir",
            str(out_dir),
        ]
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            env={**os.environ.copy(), "PYTHONPATH": str(REPO_ROOT / "src")},
            capture_output=True,
            text=True,
        )
        result["runs"].append({"index": run_idx + 1, "exit_code": proc.returncode})
        if proc.returncode != 0:
            result["exit_code"] = proc.returncode
            result["errors"].append(f"analyze command failed on run {run_idx + 1} with exit code {proc.returncode}")
            result["errors"].append((proc.stderr or proc.stdout).strip())
            return result

        findings_file = out_dir / "findings.json"
        if not findings_file.exists():
            result["errors"].append(f"findings.json was not generated on run {run_idx + 1}")
            return result

        data = json.loads(findings_file.read_text(encoding="utf-8"))
        rules = {row["rule_id"] for row in data.get("findings", [])}
        rules_per_run.append(rules)

        metrics_file = out_dir / "run_metrics.json"
        if metrics_file.exists():
            metrics_per_run.append(json.loads(metrics_file.read_text(encoding="utf-8")))

    if not rules_per_run:
        result["errors"].append("No eval runs were executed.")
        return result

    rules = rules_per_run[0]
    result["found_rules"] = sorted(rules)
    result["flaky"] = any(current != rules_per_run[0] for current in rules_per_run[1:])

    missing_required = case.required_rules - rules
    present_forbidden = case.forbidden_rules & rules
    result["required_missed_count"] = len(missing_required)
    result["forbidden_hit_count"] = len(present_forbidden)
    result["precision_proxy"] = 1.0 - (len(present_forbidden) / max(1, len(rules)))
    result["recall_proxy"] = 1.0 - (len(missing_required) / max(1, len(case.required_rules)))

    if metrics_per_run:
        result["actionability_proxy"] = _safe_mean([float(row.get("actionability_proxy", 0.0)) for row in metrics_per_run])
        result["evidence_completeness"] = _safe_mean(
            [float(row.get("evidence_completeness", 0.0)) for row in metrics_per_run]
        )
        result["verification_pass_rate"] = _safe_mean(
            [float(row.get("verification_pass_rate", 0.0)) for row in metrics_per_run]
        )
        result["fallback_rate"] = _safe_mean([1.0 if row.get("fallback_reason") else 0.0 for row in metrics_per_run])
        result["triage_time_proxy_min"] = _safe_mean([float(row.get("triage_time_proxy_min", 0.0)) for row in metrics_per_run])
    else:
        result["actionability_proxy"] = 0.0
        result["evidence_completeness"] = 0.0
        result["verification_pass_rate"] = 0.0
        result["fallback_rate"] = 0.0
        result["triage_time_proxy_min"] = 0.0

    if missing_required:
        result["errors"].append(f"missing required rules: {sorted(missing_required)}")
    if present_forbidden:
        result["errors"].append(f"found forbidden rules: {sorted(present_forbidden)}")
    if result["flaky"]:
        result["errors"].append("flaky result: rule set differs across repeated runs")

    if not result["errors"]:
        result["status"] = "passed"

    return result


def compute_aggregates(results: list[dict]) -> dict[str, float]:
    return {
        "avg_precision_proxy": _safe_mean([float(row.get("precision_proxy", 0.0)) for row in results]),
        "avg_recall_proxy": _safe_mean([float(row.get("recall_proxy", 0.0)) for row in results]),
        "avg_actionability_proxy": _safe_mean([float(row.get("actionability_proxy", 0.0)) for row in results]),
        "avg_evidence_completeness": _safe_mean([float(row.get("evidence_completeness", 0.0)) for row in results]),
        "avg_verification_pass_rate": _safe_mean([float(row.get("verification_pass_rate", 0.0)) for row in results]),
        "avg_fallback_rate": _safe_mean([float(row.get("fallback_rate", 0.0)) for row in results]),
        "avg_triage_time_proxy_min": _safe_mean([float(row.get("triage_time_proxy_min", 0.0)) for row in results]),
        "flaky_cases": float(sum(1 for row in results if row.get("flaky"))),
    }


def evaluate_trust_gates(aggregates: dict[str, float], thresholds: dict[str, float]) -> list[str]:
    errors: list[str] = []
    checks: tuple[tuple[str, str, bool], ...] = (
        (
            "avg_precision_proxy",
            "min_avg_precision_proxy",
            aggregates["avg_precision_proxy"] >= thresholds["min_avg_precision_proxy"],
        ),
        (
            "avg_recall_proxy",
            "min_avg_recall_proxy",
            aggregates["avg_recall_proxy"] >= thresholds["min_avg_recall_proxy"],
        ),
        (
            "avg_actionability_proxy",
            "min_avg_actionability_proxy",
            aggregates["avg_actionability_proxy"] >= thresholds["min_avg_actionability_proxy"],
        ),
        (
            "avg_evidence_completeness",
            "min_avg_evidence_completeness",
            aggregates["avg_evidence_completeness"] >= thresholds["min_avg_evidence_completeness"],
        ),
        (
            "avg_verification_pass_rate",
            "min_avg_verification_pass_rate",
            aggregates["avg_verification_pass_rate"] >= thresholds["min_avg_verification_pass_rate"],
        ),
        (
            "avg_triage_time_proxy_min",
            "max_avg_triage_time_proxy_min",
            aggregates["avg_triage_time_proxy_min"] <= thresholds["max_avg_triage_time_proxy_min"],
        ),
        (
            "flaky_cases",
            "max_flaky_cases",
            aggregates["flaky_cases"] <= thresholds["max_flaky_cases"],
        ),
        (
            "avg_fallback_rate",
            "max_avg_fallback_rate",
            aggregates["avg_fallback_rate"] <= thresholds["max_avg_fallback_rate"],
        ),
    )
    for metric_name, threshold_name, passed in checks:
        if passed:
            continue
        errors.append(
            f"trust gate failed: {metric_name}={aggregates[metric_name]:.4f} "
            f"violates {threshold_name}={thresholds[threshold_name]:.4f}"
        )
    return errors


def write_summary(results: list[dict], *, thresholds: dict[str, float], enforce_gates: bool) -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    aggregates = compute_aggregates(results)
    gate_errors = evaluate_trust_gates(aggregates, thresholds)
    gate_payload = {
        "status": "failed" if gate_errors else "passed",
        "enforced": enforce_gates,
        "thresholds": thresholds,
        "aggregates": aggregates,
        "errors": gate_errors,
    }
    (OUTPUT_ROOT / "trust_gate.json").write_text(json.dumps(gate_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_trend_artifacts(aggregates=aggregates, gate_payload=gate_payload)

    lines = [
        "# Eval Suite Summary",
        "",
        f"- Avg precision proxy: `{aggregates['avg_precision_proxy']:.2%}`",
        f"- Avg recall proxy: `{aggregates['avg_recall_proxy']:.2%}`",
        f"- Avg actionability proxy: `{aggregates['avg_actionability_proxy']:.2%}`",
        f"- Avg evidence completeness: `{aggregates['avg_evidence_completeness']:.2%}`",
        f"- Avg verification pass rate: `{aggregates['avg_verification_pass_rate']:.2%}`",
        f"- Avg fallback rate: `{aggregates['avg_fallback_rate']:.2%}`",
        f"- Avg triage time proxy: `{aggregates['avg_triage_time_proxy_min']:.1f} min`",
        f"- Flaky cases: `{int(aggregates['flaky_cases'])}`",
        "",
        "## Trust Gates",
        "",
        f"- Gate status: `{'FAILED' if gate_errors else 'PASSED'}`",
        f"- Enforced: `{enforce_gates}`",
        f"- min_avg_precision_proxy: `{thresholds['min_avg_precision_proxy']:.2%}`",
        f"- min_avg_recall_proxy: `{thresholds['min_avg_recall_proxy']:.2%}`",
        f"- min_avg_actionability_proxy: `{thresholds['min_avg_actionability_proxy']:.2%}`",
        f"- min_avg_evidence_completeness: `{thresholds['min_avg_evidence_completeness']:.2%}`",
        f"- min_avg_verification_pass_rate: `{thresholds['min_avg_verification_pass_rate']:.2%}`",
        f"- max_avg_fallback_rate: `{thresholds['max_avg_fallback_rate']:.2%}`",
        f"- max_avg_triage_time_proxy_min: `{thresholds['max_avg_triage_time_proxy_min']:.1f} min`",
        f"- max_flaky_cases: `{int(thresholds['max_flaky_cases'])}`",
    ]
    if gate_errors:
        lines.append("- Gate errors:")
        for err in gate_errors:
            lines.append(f"  - {err}")
    lines.append("")

    lines.extend(
        [
            "## Cases",
            "",
        ]
    )

    failures = 0
    for row in results:
        if row["status"] != "passed":
            failures += 1
        lines.append(f"### {row['case']}")
        lines.append(f"- Status: `{row['status']}`")
        lines.append(f"- Exit code: `{row['exit_code']}`")
        lines.append(f"- Found rules: `{', '.join(row['found_rules']) or 'none'}`")
        lines.append(f"- Precision proxy: `{row.get('precision_proxy', 0.0):.2%}`")
        lines.append(f"- Recall proxy: `{row.get('recall_proxy', 0.0):.2%}`")
        lines.append(f"- Actionability proxy: `{row.get('actionability_proxy', 0.0):.2%}`")
        lines.append(f"- Evidence completeness: `{row.get('evidence_completeness', 0.0):.2%}`")
        lines.append(f"- Verification pass rate: `{row.get('verification_pass_rate', 0.0):.2%}`")
        lines.append(f"- Fallback rate: `{row.get('fallback_rate', 0.0):.2%}`")
        lines.append(f"- Triage time proxy: `{row.get('triage_time_proxy_min', 0.0):.1f} min`")
        lines.append(f"- Flaky: `{row.get('flaky', False)}`")
        if row["errors"]:
            lines.append("- Errors:")
            for err in row["errors"]:
                lines.append(f"  - {err}")
        lines.append("")

    (OUTPUT_ROOT / "summary.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    if enforce_gates and gate_errors:
        failures += 1
    return failures


def main() -> int:
    if OUTPUT_ROOT.exists():
        shutil.rmtree(OUTPUT_ROOT)

    results = [run_case(case) for case in CASES]
    thresholds = load_trust_thresholds()
    enforce_gates = _parse_bool_env("AIRISK_EVAL_ENFORCE_THRESHOLDS", default=True)
    failures = write_summary(results, thresholds=thresholds, enforce_gates=enforce_gates)

    print((OUTPUT_ROOT / "summary.md").read_text(encoding="utf-8"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
