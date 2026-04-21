from __future__ import annotations

import json
import os
import shutil
import subprocess  # nosec B404
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / "eval" / "results"
HISTORY_ROOT = REPO_ROOT / "eval" / ".history"
TRUST_THRESHOLDS_PATH = REPO_ROOT / "eval" / "trust_thresholds.json"
SUPPORT_LEVEL_PROMOTION_PATH = REPO_ROOT / "eval" / "support_level_promotion.json"
CAPABILITY_PACK_PROMOTION_PATH = REPO_ROOT / "eval" / "capability_pack_promotion.json"
DEFAULT_HISTORY_PATH = HISTORY_ROOT / "trust_gate_history.jsonl"
DEFAULT_TREND_WINDOW = 12
DEFAULT_EXPANSION_GATE_CONSECUTIVE_RUNS = 4
EXPANSION_REQUIRED_CASES = {
    "milestone7_django_viewset",
    "milestone8_django_dependency",
    "milestone10_express_authz_gap",
    "milestone11_express_balanced",
}
PERCENT_METRICS = {
    "avg_precision_proxy",
    "avg_recall_proxy",
    "avg_actionability_proxy",
    "avg_evidence_completeness",
    "avg_verification_pass_rate",
    "avg_fallback_rate",
}
MIN_AVG_VERIFICATION_PASS_RATE_KEY = "min_avg_verification_" + "pass_rate"
VERIFICATION_PASS_RATE_KEY = "verification_" + "pass_rate"
DEFAULT_TRUST_THRESHOLDS: dict[str, float] = {
    "min_avg_precision_proxy": 0.75,
    "min_avg_recall_proxy": 0.75,
    "min_avg_actionability_proxy": 0.40,
    "min_avg_evidence_completeness": 0.95,
    MIN_AVG_VERIFICATION_PASS_RATE_KEY: 0.95,
    "max_avg_triage_time_proxy_min": 10.0,
    "max_flaky_cases": 0.0,
    "max_avg_fallback_rate": 0.15,
}
DEFAULT_SUPPORT_LEVEL_PROMOTION_POLICY: dict[str, object] = {
    "version": 1,
    "stacks": {
        "fastapi_pytest": {
            "eligible_level": "l2",
            "required_cases": ["milestone2_fastapi", "milestone5_balanced"],
            "required_consecutive_trust_passes": 2,
        },
        "django_drf": {
            "eligible_level": "l2",
            "required_cases": ["milestone7_django_viewset", "milestone8_django_dependency"],
            "required_consecutive_trust_passes": 2,
        },
        "express_node": {
            "eligible_level": "l2",
            "required_cases": [
                "milestone10_express_authz_gap",
                "milestone11_express_balanced",
                "milestone12_express_integrity_gap",
                "milestone12_express_integrity_balanced",
                "milestone13_express_html_gap",
                "milestone13_express_html_balanced",
                "milestone14_express_ui_gap",
                "milestone14_express_ui_balanced",
            ],
            "required_consecutive_trust_passes": 2,
        },
    },
}
DEFAULT_CAPABILITY_PACK_PROMOTION_POLICY: dict[str, object] = {
    "version": 1,
    "packs": {
        "express_stage11_p0_integrity": {
            "stack_id": "express_node",
            "eligible_level": "l2",
            "required_cases": [
                "milestone12_express_integrity_gap",
                "milestone12_express_integrity_balanced",
            ],
            "required_consecutive_trust_passes": 2,
        },
        "express_stage11_p1_html_sink": {
            "stack_id": "express_node",
            "eligible_level": "l2",
            "required_cases": [
                "milestone13_express_html_gap",
                "milestone13_express_html_balanced",
            ],
            "required_consecutive_trust_passes": 2,
        },
        "express_stage11_p2_ui_ergonomics": {
            "stack_id": "express_node",
            "eligible_level": "l2",
            "required_cases": [
                "milestone14_express_ui_gap",
                "milestone14_express_ui_balanced",
            ],
            "required_consecutive_trust_passes": 2,
        },
        "fastapi_stage14_write_contract_integrity": {
            "stack_id": "fastapi_pytest",
            "eligible_level": "l2",
            "required_cases": [
                "milestone18_fastapi_integrity_gap",
                "milestone18_fastapi_integrity_balanced",
            ],
            "required_consecutive_trust_passes": 2,
        },
        "fastapi_stage14_session_lifecycle": {
            "stack_id": "fastapi_pytest",
            "eligible_level": "l2",
            "required_cases": [
                "milestone20_fastapi_session_gap",
                "milestone20_fastapi_session_balanced",
            ],
            "required_consecutive_trust_passes": 2,
        },
        "django_stage14_write_contract_integrity": {
            "stack_id": "django_drf",
            "eligible_level": "l2",
            "required_cases": [
                "milestone19_django_integrity_gap",
                "milestone19_django_integrity_balanced",
            ],
            "required_consecutive_trust_passes": 2,
        },
        "django_stage14_session_lifecycle": {
            "stack_id": "django_drf",
            "eligible_level": "l2",
            "required_cases": [
                "milestone21_django_session_gap",
                "milestone21_django_session_balanced",
            ],
            "required_consecutive_trust_passes": 2,
        },
    },
}

if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from ai_risk_manager.collectors.plugins.contract import PLUGIN_CONTRACT_VERSION  # noqa: E402
from ai_risk_manager.collectors.plugins.registry import evaluate_registered_plugin_conformance, get_signal_plugin_for_stack  # noqa: E402
from ai_risk_manager.stacks.discovery import detect_stack  # noqa: E402


@dataclass
class EvalCase:
    name: str
    repo_rel: str
    required_rules: set[str]
    forbidden_rules: set[str]
    required_ingress_families: set[str] | None = None
    required_coverage_families: set[str] | None = None


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
    EvalCase(
        name="milestone6_coverage_aliases",
        repo_rel="eval/repos/milestone6_coverage_aliases",
        required_rules=set(),
        forbidden_rules={"critical_path_no_tests"},
    ),
    EvalCase(
        name="milestone7_django_viewset",
        repo_rel="eval/repos/milestone7_django_viewset",
        required_rules=set(),
        forbidden_rules={"critical_path_no_tests"},
    ),
    EvalCase(
        name="milestone8_django_dependency",
        repo_rel="eval/repos/milestone8_django_dependency",
        required_rules={"dependency_risk_policy_violation"},
        forbidden_rules={"critical_path_no_tests"},
    ),
    EvalCase(
        name="milestone9_django_missing_tests",
        repo_rel="eval/repos/milestone9_django_missing_tests",
        required_rules={"critical_path_no_tests"},
        forbidden_rules={"dependency_risk_policy_violation"},
    ),
    EvalCase(
        name="milestone10_express_authz_gap",
        repo_rel="eval/repos/milestone10_express_authz_gap",
        required_rules={"critical_path_no_tests", "critical_write_missing_authz"},
        forbidden_rules=set(),
    ),
    EvalCase(
        name="milestone11_express_balanced",
        repo_rel="eval/repos/milestone11_express_balanced",
        required_rules=set(),
        forbidden_rules={"critical_path_no_tests", "critical_write_missing_authz"},
    ),
    EvalCase(
        name="milestone12_express_integrity_gap",
        repo_rel="eval/repos/milestone12_express_integrity_gap",
        required_rules={
            "input_normalization_char_split",
            "response_field_contract_mismatch",
            "db_insert_binding_mismatch",
            "critical_write_scope_missing_entity_filter",
            "stale_write_without_conflict_guard",
            "session_token_key_mismatch",
        },
        forbidden_rules={"critical_path_no_tests", "critical_write_missing_authz"},
    ),
    EvalCase(
        name="milestone12_express_integrity_balanced",
        repo_rel="eval/repos/milestone12_express_integrity_balanced",
        required_rules=set(),
        forbidden_rules={
            "input_normalization_char_split",
            "response_field_contract_mismatch",
            "db_insert_binding_mismatch",
            "critical_write_scope_missing_entity_filter",
            "stale_write_without_conflict_guard",
            "session_token_key_mismatch",
            "critical_path_no_tests",
            "critical_write_missing_authz",
        },
    ),
    EvalCase(
        name="milestone13_express_html_gap",
        repo_rel="eval/repos/milestone13_express_html_gap",
        required_rules={"stored_xss_unsafe_innerhtml"},
        forbidden_rules={"critical_path_no_tests", "critical_write_missing_authz"},
    ),
    EvalCase(
        name="milestone13_express_html_balanced",
        repo_rel="eval/repos/milestone13_express_html_balanced",
        required_rules=set(),
        forbidden_rules={
            "stored_xss_unsafe_innerhtml",
            "critical_path_no_tests",
            "critical_write_missing_authz",
        },
    ),
    EvalCase(
        name="milestone14_express_ui_gap",
        repo_rel="eval/repos/milestone14_express_ui_gap",
        required_rules={
            "pagination_page_not_normalized",
            "save_button_partial_form_enabled",
            "mobile_layout_min_width_overflow",
        },
        forbidden_rules={"critical_path_no_tests", "critical_write_missing_authz"},
    ),
    EvalCase(
        name="milestone14_express_ui_balanced",
        repo_rel="eval/repos/milestone14_express_ui_balanced",
        required_rules=set(),
        forbidden_rules={
            "pagination_page_not_normalized",
            "save_button_partial_form_enabled",
            "mobile_layout_min_width_overflow",
            "critical_path_no_tests",
            "critical_write_missing_authz",
        },
    ),
    EvalCase(
        name="milestone15_fastapi_webhook_ingress",
        repo_rel="eval/repos/milestone15_fastapi_webhook_ingress",
        required_rules=set(),
        forbidden_rules={"critical_path_no_tests"},
        required_ingress_families={"webhook"},
        required_coverage_families={"webhook"},
    ),
    EvalCase(
        name="milestone16_express_job_cli_ingress",
        repo_rel="eval/repos/milestone16_express_job_cli_ingress",
        required_rules=set(),
        forbidden_rules={"critical_path_no_tests"},
        required_ingress_families={"job", "cli_task"},
        required_coverage_families={"job", "cli_task"},
    ),
    EvalCase(
        name="milestone17_express_event_consumer_ingress",
        repo_rel="eval/repos/milestone17_express_event_consumer_ingress",
        required_rules=set(),
        forbidden_rules={"critical_path_no_tests"},
        required_ingress_families={"event_consumer"},
        required_coverage_families={"event_consumer"},
    ),
    EvalCase(
        name="milestone18_fastapi_integrity_gap",
        repo_rel="eval/repos/milestone18_fastapi_integrity_gap",
        required_rules={
            "critical_write_scope_missing_entity_filter",
            "stale_write_without_conflict_guard",
        },
        forbidden_rules={"critical_path_no_tests"},
    ),
    EvalCase(
        name="milestone18_fastapi_integrity_balanced",
        repo_rel="eval/repos/milestone18_fastapi_integrity_balanced",
        required_rules=set(),
        forbidden_rules={
            "critical_write_scope_missing_entity_filter",
            "stale_write_without_conflict_guard",
            "critical_path_no_tests",
        },
    ),
    EvalCase(
        name="milestone19_django_integrity_gap",
        repo_rel="eval/repos/milestone19_django_integrity_gap",
        required_rules={
            "critical_write_scope_missing_entity_filter",
            "stale_write_without_conflict_guard",
        },
        forbidden_rules={"critical_path_no_tests"},
    ),
    EvalCase(
        name="milestone19_django_integrity_balanced",
        repo_rel="eval/repos/milestone19_django_integrity_balanced",
        required_rules=set(),
        forbidden_rules={
            "critical_write_scope_missing_entity_filter",
            "stale_write_without_conflict_guard",
            "critical_path_no_tests",
        },
    ),
    EvalCase(
        name="milestone20_fastapi_session_gap",
        repo_rel="eval/repos/milestone20_fastapi_session_gap",
        required_rules={"session_token_key_mismatch"},
        forbidden_rules={"critical_path_no_tests"},
    ),
    EvalCase(
        name="milestone20_fastapi_session_balanced",
        repo_rel="eval/repos/milestone20_fastapi_session_balanced",
        required_rules=set(),
        forbidden_rules={
            "session_token_key_mismatch",
            "critical_path_no_tests",
        },
    ),
    EvalCase(
        name="milestone21_django_session_gap",
        repo_rel="eval/repos/milestone21_django_session_gap",
        required_rules={"session_token_key_mismatch"},
        forbidden_rules={"critical_path_no_tests"},
    ),
    EvalCase(
        name="milestone21_django_session_balanced",
        repo_rel="eval/repos/milestone21_django_session_balanced",
        required_rules=set(),
        forbidden_rules={
            "session_token_key_mismatch",
            "critical_path_no_tests",
        },
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


def _count_consecutive_trust_passes(history: list[dict]) -> int:
    count = 0
    for row in reversed(history):
        if str(row.get("gate_status")) != "passed":
            break
        count += 1
    return count


def build_expansion_gate_payload(
    results: list[dict],
    history: list[dict],
    *,
    required_consecutive_passes: int | None = None,
) -> dict[str, object]:
    required_runs = required_consecutive_passes or _parse_positive_int_env(
        "AIRISK_EXPANSION_GATE_CONSECUTIVE_RUNS",
        DEFAULT_EXPANSION_GATE_CONSECUTIVE_RUNS,
    )
    result_by_case = {str(row.get("case")): row for row in results}
    required_cases = sorted(EXPANSION_REQUIRED_CASES)
    missing_required_cases = sorted(case for case in required_cases if case not in result_by_case)
    failing_required_cases = sorted(
        case for case in required_cases if case in result_by_case and str(result_by_case[case].get("status")) != "passed"
    )

    latest_gate_status = str(history[-1].get("gate_status")) if history else "unknown"
    consecutive_passes = _count_consecutive_trust_passes(history)
    ready_by_consecutive_passes = consecutive_passes >= required_runs
    expansion_gate_open = (
        latest_gate_status == "passed"
        and ready_by_consecutive_passes
        and not missing_required_cases
        and not failing_required_cases
    )

    reasons: list[str] = []
    if latest_gate_status != "passed":
        reasons.append("latest trust gate status is not passed")
    if not ready_by_consecutive_passes:
        reasons.append(
            f"consecutive passed trust runs is {consecutive_passes}, requires >= {required_runs}"
        )
    if missing_required_cases:
        reasons.append(f"missing required expansion eval cases: {missing_required_cases}")
    if failing_required_cases:
        reasons.append(f"required expansion eval cases are not passed: {failing_required_cases}")

    return {
        "status": "open" if expansion_gate_open else "closed",
        "required_consecutive_passes": required_runs,
        "consecutive_passes": consecutive_passes,
        "latest_trust_gate_status": latest_gate_status,
        "required_cases": required_cases,
        "missing_required_cases": missing_required_cases,
        "failing_required_cases": failing_required_cases,
        "reasons": reasons,
    }


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


def load_support_level_promotion_policy(path: Path = SUPPORT_LEVEL_PROMOTION_PATH) -> dict[str, object]:
    policy: dict[str, object] = dict(DEFAULT_SUPPORT_LEVEL_PROMOTION_POLICY)
    if not path.is_file():
        return policy
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return policy
    if not isinstance(payload, dict):
        return policy

    version = payload.get("version", 1)
    stacks = payload.get("stacks", {})
    if not isinstance(version, int) or not isinstance(stacks, dict):
        return policy

    normalized_stacks: dict[str, dict[str, object]] = {}
    for stack_id, raw in stacks.items():
        if not isinstance(stack_id, str) or not isinstance(raw, dict):
            continue
        eligible_level = raw.get("eligible_level", "l2")
        required_cases = raw.get("required_cases", [])
        required_passes = raw.get("required_consecutive_trust_passes", 1)
        if (
            isinstance(eligible_level, str)
            and isinstance(required_cases, list)
            and isinstance(required_passes, int)
            and required_passes >= 1
        ):
            normalized_cases = [str(item) for item in required_cases if isinstance(item, str)]
            normalized_stacks[stack_id] = {
                "eligible_level": eligible_level,
                "required_cases": normalized_cases,
                "required_consecutive_trust_passes": required_passes,
            }

    if not normalized_stacks:
        return policy
    return {
        "version": version,
        "stacks": normalized_stacks,
    }


def load_capability_pack_promotion_policy(path: Path = CAPABILITY_PACK_PROMOTION_PATH) -> dict[str, object]:
    policy: dict[str, object] = dict(DEFAULT_CAPABILITY_PACK_PROMOTION_POLICY)
    if not path.is_file():
        return policy
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return policy
    if not isinstance(payload, dict):
        return policy

    version = payload.get("version", 1)
    packs = payload.get("packs", {})
    if not isinstance(version, int) or not isinstance(packs, dict):
        return policy

    normalized_packs: dict[str, dict[str, object]] = {}
    for pack_id, raw in packs.items():
        if not isinstance(pack_id, str) or not isinstance(raw, dict):
            continue
        stack_id = raw.get("stack_id", "")
        eligible_level = raw.get("eligible_level", "l2")
        required_cases = raw.get("required_cases", [])
        required_passes = raw.get("required_consecutive_trust_passes", 1)
        if (
            isinstance(stack_id, str)
            and isinstance(eligible_level, str)
            and isinstance(required_cases, list)
            and isinstance(required_passes, int)
            and required_passes >= 1
        ):
            normalized_packs[pack_id] = {
                "stack_id": stack_id,
                "eligible_level": eligible_level,
                "required_cases": [str(item) for item in required_cases if isinstance(item, str)],
                "required_consecutive_trust_passes": required_passes,
            }

    if not normalized_packs:
        return policy
    return {
        "version": version,
        "packs": normalized_packs,
    }


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
        VERIFICATION_PASS_RATE_KEY: 1.0,
        "fallback_rate": 0.0,
        "triage_time_proxy_min": 0.0,
        "flaky": False,
        "status": "failed",
        "errors": [],
        "required_ingress_families": sorted(case.required_ingress_families or set()),
        "required_coverage_families": sorted(case.required_coverage_families or set()),
        "found_ingress_families": [],
        "found_coverage_families": [],
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
        # Eval command argv is constructed internally and shell=False.
        proc = subprocess.run(  # nosec B603
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

    if case.required_ingress_families or case.required_coverage_families:
        _evaluate_ingress_expectations(case, repo_path, result)

    if not result["errors"]:
        result["status"] = "passed"

    return result


def _evaluate_ingress_expectations(case: EvalCase, repo_path: Path, result: dict[str, object]) -> None:
    detection = detect_stack(repo_path)
    plugin = get_signal_plugin_for_stack(detection.stack_id)
    if plugin is None:
        result.setdefault("errors", []).append(f"no signal plugin registered for stack '{detection.stack_id}'")
        return

    artifacts = plugin.collect(repo_path)
    signals = plugin.collect_signals_from_artifacts(artifacts)
    found_ingress = {
        str(signal.attributes.get("family", "")).strip()
        for signal in signals.signals
        if signal.kind == "ingress_surface"
    }
    found_coverage = {
        str(signal.attributes.get("family", "")).strip()
        for signal in signals.signals
        if signal.kind == "test_to_ingress_coverage"
    }
    result["found_ingress_families"] = sorted(family for family in found_ingress if family)
    result["found_coverage_families"] = sorted(family for family in found_coverage if family)

    missing_ingress = sorted((case.required_ingress_families or set()) - found_ingress)
    missing_coverage = sorted((case.required_coverage_families or set()) - found_coverage)
    if missing_ingress:
        result.setdefault("errors", []).append(f"missing required ingress families: {missing_ingress}")
    if missing_coverage:
        result.setdefault("errors", []).append(f"missing required ingress coverage families: {missing_coverage}")


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


def build_plugin_conformance_payload() -> dict[str, object]:
    reports = evaluate_registered_plugin_conformance()
    errors: list[str] = []
    plugin_rows: list[dict[str, object]] = []
    for report in reports:
        plugin_rows.append(
            {
                "stack_id": report.stack_id,
                "plugin_contract_version": report.plugin_contract_version,
                "target_support_level": report.target_support_level,
                "status": "passed" if report.passed else "failed",
                "capability_matrix": report.capability_matrix,
                "errors": report.errors,
            }
        )
        if report.errors:
            errors.extend(f"{report.stack_id}: {message}" for message in report.errors)

    return {
        "plugin_contract_version": PLUGIN_CONTRACT_VERSION,
        "status": "failed" if errors else "passed",
        "plugins": plugin_rows,
        "errors": errors,
    }


def build_support_level_promotion_payload(
    *,
    results: list[dict],
    trend_history: list[dict],
    trust_gate_payload: dict[str, object],
    plugin_conformance_payload: dict[str, object],
    policy: dict[str, object],
) -> dict[str, object]:
    result_by_case = {str(row.get("case")): str(row.get("status")) for row in results}
    plugin_rows = plugin_conformance_payload.get("plugins", [])
    plugin_status_by_stack: dict[str, str] = {}
    if isinstance(plugin_rows, list):
        for row in plugin_rows:
            if not isinstance(row, dict):
                continue
            stack_id = row.get("stack_id")
            status = row.get("status")
            if isinstance(stack_id, str) and isinstance(status, str):
                plugin_status_by_stack[stack_id] = status

    trust_passed = str(trust_gate_payload.get("status")) == "passed"
    consecutive_trust_passes = _count_consecutive_trust_passes(trend_history)
    stacks_policy = policy.get("stacks", {})
    stack_rows: list[dict[str, object]] = []
    for stack_id, raw in stacks_policy.items():
        if not isinstance(stack_id, str) or not isinstance(raw, dict):
            continue
        eligible_level = str(raw.get("eligible_level", "l2"))
        required_cases = [str(item) for item in raw.get("required_cases", []) if isinstance(item, str)]
        required_passes = int(raw.get("required_consecutive_trust_passes", 1))
        missing_cases = [case for case in required_cases if case not in result_by_case]
        failing_cases = [case for case in required_cases if result_by_case.get(case) not in {None, "passed"}]
        plugin_status = plugin_status_by_stack.get(stack_id, "missing")
        plugin_ok = plugin_status == "passed"
        trust_ok = trust_passed and consecutive_trust_passes >= required_passes
        reasons: list[str] = []
        if not plugin_ok:
            reasons.append(f"plugin conformance status is '{plugin_status}'")
        if not trust_ok:
            reasons.append(
                "trust gate requirement not satisfied "
                f"(consecutive={consecutive_trust_passes}, required={required_passes}, status={trust_gate_payload.get('status')})"
            )
        if missing_cases:
            reasons.append(f"missing required eval cases: {missing_cases}")
        if failing_cases:
            reasons.append(f"required eval cases not passed: {failing_cases}")

        stack_rows.append(
            {
                "stack_id": stack_id,
                "eligible_level": eligible_level,
                "status": "eligible" if not reasons else "blocked",
                "required_cases": required_cases,
                "missing_cases": missing_cases,
                "failing_cases": failing_cases,
                "required_consecutive_trust_passes": required_passes,
                "consecutive_trust_passes": consecutive_trust_passes,
                "plugin_conformance_status": plugin_status,
                "reasons": reasons,
            }
        )

    return {
        "version": policy.get("version", 1),
        "status": "ready" if stack_rows and all(row["status"] == "eligible" for row in stack_rows) else "blocked",
        "stacks": stack_rows,
    }


def build_capability_pack_promotion_payload(
    *,
    results: list[dict],
    trend_history: list[dict],
    trust_gate_payload: dict[str, object],
    policy: dict[str, object],
) -> dict[str, object]:
    result_by_case = {str(row.get("case")): str(row.get("status")) for row in results}
    trust_passed = str(trust_gate_payload.get("status")) == "passed"
    consecutive_trust_passes = _count_consecutive_trust_passes(trend_history)
    packs_policy = policy.get("packs", {})
    pack_rows: list[dict[str, object]] = []
    for pack_id, raw in packs_policy.items():
        if not isinstance(pack_id, str) or not isinstance(raw, dict):
            continue
        stack_id = str(raw.get("stack_id", "unknown"))
        eligible_level = str(raw.get("eligible_level", "l2"))
        required_cases = [str(item) for item in raw.get("required_cases", []) if isinstance(item, str)]
        required_passes = int(raw.get("required_consecutive_trust_passes", 1))
        missing_cases = [case for case in required_cases if case not in result_by_case]
        failing_cases = [case for case in required_cases if result_by_case.get(case) not in {None, "passed"}]
        trust_ok = trust_passed and consecutive_trust_passes >= required_passes
        reasons: list[str] = []
        if not trust_ok:
            reasons.append(
                "trust gate requirement not satisfied "
                f"(consecutive={consecutive_trust_passes}, required={required_passes}, status={trust_gate_payload.get('status')})"
            )
        if missing_cases:
            reasons.append(f"missing required eval cases: {missing_cases}")
        if failing_cases:
            reasons.append(f"required eval cases not passed: {failing_cases}")

        pack_rows.append(
            {
                "pack_id": pack_id,
                "stack_id": stack_id,
                "eligible_level": eligible_level,
                "status": "eligible" if not reasons else "blocked",
                "required_cases": required_cases,
                "missing_cases": missing_cases,
                "failing_cases": failing_cases,
                "required_consecutive_trust_passes": required_passes,
                "consecutive_trust_passes": consecutive_trust_passes,
                "reasons": reasons,
            }
        )

    return {
        "version": policy.get("version", 1),
        "status": "ready" if pack_rows and all(row["status"] == "eligible" for row in pack_rows) else "blocked",
        "packs": pack_rows,
    }


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
    trend_history = load_trend_history(OUTPUT_ROOT / "trust_history.jsonl")
    expansion_gate_payload = build_expansion_gate_payload(results, trend_history)
    (OUTPUT_ROOT / "expansion_gate.json").write_text(
        json.dumps(expansion_gate_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    plugin_conformance_payload = build_plugin_conformance_payload()
    (OUTPUT_ROOT / "plugin_conformance.json").write_text(
        json.dumps(plugin_conformance_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    promotion_policy = load_support_level_promotion_policy()
    support_level_promotion_payload = build_support_level_promotion_payload(
        results=results,
        trend_history=trend_history,
        trust_gate_payload=gate_payload,
        plugin_conformance_payload=plugin_conformance_payload,
        policy=promotion_policy,
    )
    (OUTPUT_ROOT / "support_level_promotion.json").write_text(
        json.dumps(support_level_promotion_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    capability_pack_policy = load_capability_pack_promotion_policy()
    capability_pack_promotion_payload = build_capability_pack_promotion_payload(
        results=results,
        trend_history=trend_history,
        trust_gate_payload=gate_payload,
        policy=capability_pack_policy,
    )
    (OUTPUT_ROOT / "capability_pack_promotion.json").write_text(
        json.dumps(capability_pack_promotion_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

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
    lines.extend(
        [
            "",
            "## Expansion Gate",
            "",
            f"- Gate status: `{str(expansion_gate_payload['status']).upper()}`",
            f"- Required consecutive trust-pass runs: `{expansion_gate_payload['required_consecutive_passes']}`",
            f"- Current consecutive trust-pass runs: `{expansion_gate_payload['consecutive_passes']}`",
            f"- Required expansion eval cases: `{', '.join(expansion_gate_payload['required_cases'])}`",
        ]
    )
    if expansion_gate_payload["reasons"]:
        lines.append("- Gate reasons:")
        for reason in expansion_gate_payload["reasons"]:
            lines.append(f"  - {reason}")
    lines.extend(
        [
            "",
            "## Plugin Conformance",
            "",
            f"- Contract version: `{plugin_conformance_payload['plugin_contract_version']}`",
            f"- Gate status: `{str(plugin_conformance_payload['status']).upper()}`",
        ]
    )
    if plugin_conformance_payload["errors"]:
        lines.append("- Gate errors:")
        for reason in plugin_conformance_payload["errors"]:
            lines.append(f"  - {reason}")
    lines.extend(
        [
            "",
            "## Support-Level Promotion",
            "",
            f"- Gate status: `{str(support_level_promotion_payload['status']).upper()}`",
        ]
    )
    for stack_row in support_level_promotion_payload["stacks"]:
        lines.append(
            f"- {stack_row['stack_id']} -> {stack_row['eligible_level']}: "
            f"`{str(stack_row['status']).upper()}`"
        )
        if stack_row["reasons"]:
            lines.append(f"  - reasons: {', '.join(str(item) for item in stack_row['reasons'])}")
    lines.extend(
        [
            "",
            "## Capability-Pack Promotion",
            "",
            f"- Gate status: `{str(capability_pack_promotion_payload['status']).upper()}`",
        ]
    )
    for pack_row in capability_pack_promotion_payload["packs"]:
        lines.append(
            f"- {pack_row['pack_id']} ({pack_row['stack_id']}) -> {pack_row['eligible_level']}: "
            f"`{str(pack_row['status']).upper()}`"
        )
        if pack_row["reasons"]:
            lines.append(f"  - reasons: {', '.join(str(item) for item in pack_row['reasons'])}")
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
    if plugin_conformance_payload["status"] != "passed":
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
