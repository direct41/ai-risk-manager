from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_eval_suite.py"
SPEC = importlib.util.spec_from_file_location("run_eval_suite", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
run_eval_suite = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = run_eval_suite
SPEC.loader.exec_module(run_eval_suite)


def test_load_trust_thresholds_uses_defaults_for_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"
    loaded = run_eval_suite.load_trust_thresholds(path)

    assert loaded["min_avg_precision_proxy"] == 0.75
    assert loaded["max_flaky_cases"] == 0.0


def test_evaluate_trust_gates_detects_threshold_breach() -> None:
    aggregates = {
        "avg_precision_proxy": 0.60,
        "avg_recall_proxy": 0.80,
        "avg_actionability_proxy": 0.50,
        "avg_evidence_completeness": 0.96,
        "avg_verification_pass_rate": 0.97,
        "avg_fallback_rate": 0.10,
        "avg_triage_time_proxy_min": 8.0,
        "flaky_cases": 0.0,
    }
    thresholds = dict(run_eval_suite.DEFAULT_TRUST_THRESHOLDS)

    errors = run_eval_suite.evaluate_trust_gates(aggregates, thresholds)

    assert errors
    assert any("avg_precision_proxy" in err for err in errors)


def test_evaluate_trust_gates_passes_on_healthy_aggregates() -> None:
    aggregates = {
        "avg_precision_proxy": 0.90,
        "avg_recall_proxy": 0.90,
        "avg_actionability_proxy": 0.60,
        "avg_evidence_completeness": 0.99,
        "avg_verification_pass_rate": 0.99,
        "avg_fallback_rate": 0.00,
        "avg_triage_time_proxy_min": 4.0,
        "flaky_cases": 0.0,
    }

    errors = run_eval_suite.evaluate_trust_gates(aggregates, dict(run_eval_suite.DEFAULT_TRUST_THRESHOLDS))

    assert errors == []


def test_load_trend_history_skips_non_json_lines(tmp_path: Path) -> None:
    history_path = tmp_path / "trust_gate_history.jsonl"
    history_path.write_text(
        "\n".join(
            [
                '{"generated_at_utc":"2026-01-01T00:00:00Z","gate_status":"passed","aggregates":{"avg_precision_proxy":0.9}}',
                "not-json",
                "42",
                '{"generated_at_utc":"2026-01-08T00:00:00Z","gate_status":"failed","aggregates":{"avg_precision_proxy":0.7}}',
            ]
        ),
        encoding="utf-8",
    )

    loaded = run_eval_suite.load_trend_history(history_path)

    assert len(loaded) == 2
    assert loaded[0]["gate_status"] == "passed"
    assert loaded[1]["gate_status"] == "failed"


def test_write_trend_artifacts_generates_history_and_delta(tmp_path: Path) -> None:
    output_root = tmp_path / "results"
    output_root.mkdir(parents=True, exist_ok=True)
    history_path = tmp_path / "history" / "trust_gate_history.jsonl"

    first_aggregates = {
        "avg_precision_proxy": 0.80,
        "avg_recall_proxy": 0.85,
        "avg_actionability_proxy": 0.50,
        "avg_evidence_completeness": 0.98,
        "avg_verification_pass_rate": 0.97,
        "avg_fallback_rate": 0.10,
        "avg_triage_time_proxy_min": 6.0,
        "flaky_cases": 0.0,
    }
    second_aggregates = dict(first_aggregates)
    second_aggregates["avg_precision_proxy"] = 0.90
    second_aggregates["avg_fallback_rate"] = 0.05

    with patch.object(run_eval_suite, "_utc_now_iso", side_effect=["2026-01-01T00:00:00Z", "2026-01-08T00:00:00Z"]):
        run_eval_suite.write_trend_artifacts(
            aggregates=first_aggregates,
            gate_payload={"status": "passed"},
            output_root=output_root,
            history_path=history_path,
            trend_window=12,
        )
        run_eval_suite.write_trend_artifacts(
            aggregates=second_aggregates,
            gate_payload={"status": "passed"},
            output_root=output_root,
            history_path=history_path,
            trend_window=12,
        )

    history_lines = history_path.read_text(encoding="utf-8").splitlines()
    assert len(history_lines) == 2

    trend_payload = json.loads((output_root / "trust_trend.json").read_text(encoding="utf-8"))
    assert trend_payload["window_size"] == 2
    assert trend_payload["latest"]["generated_at_utc"] == "2026-01-08T00:00:00Z"
    assert abs(trend_payload["delta_vs_previous"]["avg_precision_proxy"] - 0.10) < 1e-9
    assert abs(trend_payload["delta_vs_previous"]["avg_fallback_rate"] + 0.05) < 1e-9

    trend_md = (output_root / "trust_trend.md").read_text(encoding="utf-8")
    assert "Delta vs Previous Run" in trend_md
    assert "avg_precision_proxy" in trend_md


def test_write_trend_artifacts_applies_window_limit(tmp_path: Path) -> None:
    output_root = tmp_path / "results"
    output_root.mkdir(parents=True, exist_ok=True)
    history_path = tmp_path / "history" / "trust_gate_history.jsonl"
    aggregates = {
        "avg_precision_proxy": 0.80,
        "avg_recall_proxy": 0.80,
        "avg_actionability_proxy": 0.50,
        "avg_evidence_completeness": 0.98,
        "avg_verification_pass_rate": 0.97,
        "avg_fallback_rate": 0.10,
        "avg_triage_time_proxy_min": 6.0,
        "flaky_cases": 0.0,
    }

    with patch.object(
        run_eval_suite,
        "_utc_now_iso",
        side_effect=[
            "2026-01-01T00:00:00Z",
            "2026-01-08T00:00:00Z",
            "2026-01-15T00:00:00Z",
        ],
    ):
        run_eval_suite.write_trend_artifacts(
            aggregates=aggregates,
            gate_payload={"status": "passed"},
            output_root=output_root,
            history_path=history_path,
            trend_window=2,
        )
        run_eval_suite.write_trend_artifacts(
            aggregates=aggregates,
            gate_payload={"status": "passed"},
            output_root=output_root,
            history_path=history_path,
            trend_window=2,
        )
        run_eval_suite.write_trend_artifacts(
            aggregates=aggregates,
            gate_payload={"status": "passed"},
            output_root=output_root,
            history_path=history_path,
            trend_window=2,
        )

    history_payload = run_eval_suite.load_trend_history(history_path)
    assert len(history_payload) == 2
    assert history_payload[0]["generated_at_utc"] == "2026-01-08T00:00:00Z"
    assert history_payload[1]["generated_at_utc"] == "2026-01-15T00:00:00Z"


def test_count_consecutive_trust_passes_uses_trailing_window() -> None:
    history = [
        {"gate_status": "passed"},
        {"gate_status": "failed"},
        {"gate_status": "passed"},
        {"gate_status": "passed"},
    ]

    count = run_eval_suite._count_consecutive_trust_passes(history)

    assert count == 2


def test_build_expansion_gate_payload_closes_when_required_case_fails() -> None:
    results = [
        {"case": "milestone7_django_viewset", "status": "passed"},
        {"case": "milestone8_django_dependency", "status": "failed"},
    ]
    history = [
        {"gate_status": "passed"},
        {"gate_status": "passed"},
        {"gate_status": "passed"},
        {"gate_status": "passed"},
    ]

    payload = run_eval_suite.build_expansion_gate_payload(results, history, required_consecutive_passes=4)

    assert payload["status"] == "closed"
    assert payload["consecutive_passes"] == 4
    assert payload["failing_required_cases"] == ["milestone8_django_dependency"]
    assert payload["reasons"]


def test_build_support_level_promotion_payload_marks_stack_blocked_on_case_failure() -> None:
    results = [
        {"case": "milestone7_django_viewset", "status": "passed"},
        {"case": "milestone8_django_dependency", "status": "failed"},
    ]
    history = [
        {"gate_status": "passed"},
        {"gate_status": "passed"},
    ]
    trust_gate = {"status": "passed"}
    plugin_conformance = {
        "status": "passed",
        "plugins": [
            {"stack_id": "django_drf", "status": "passed"},
        ],
    }
    policy = {
        "version": 1,
        "stacks": {
            "django_drf": {
                "eligible_level": "l2",
                "required_cases": ["milestone7_django_viewset", "milestone8_django_dependency"],
                "required_consecutive_trust_passes": 2,
            }
        },
    }

    payload = run_eval_suite.build_support_level_promotion_payload(
        results=results,
        trend_history=history,
        trust_gate_payload=trust_gate,
        plugin_conformance_payload=plugin_conformance,
        policy=policy,
    )

    assert payload["status"] == "blocked"
    assert payload["stacks"][0]["status"] == "blocked"
    assert payload["stacks"][0]["failing_cases"] == ["milestone8_django_dependency"]


def test_write_summary_writes_expansion_gate_artifact(tmp_path: Path) -> None:
    output_root = tmp_path / "results"
    thresholds = dict(run_eval_suite.DEFAULT_TRUST_THRESHOLDS)
    results = [
        {
            "case": "milestone7_django_viewset",
            "status": "passed",
            "exit_code": 0,
            "found_rules": [],
            "precision_proxy": 1.0,
            "recall_proxy": 1.0,
            "actionability_proxy": 1.0,
            "evidence_completeness": 1.0,
            "verification_pass_rate": 1.0,
            "fallback_rate": 0.0,
            "triage_time_proxy_min": 1.0,
            "flaky": False,
            "errors": [],
        },
        {
            "case": "milestone8_django_dependency",
            "status": "passed",
            "exit_code": 0,
            "found_rules": ["dependency_risk_policy_violation"],
            "precision_proxy": 1.0,
            "recall_proxy": 1.0,
            "actionability_proxy": 1.0,
            "evidence_completeness": 1.0,
            "verification_pass_rate": 1.0,
            "fallback_rate": 0.0,
            "triage_time_proxy_min": 1.0,
            "flaky": False,
            "errors": [],
        },
    ]

    with patch.dict(os.environ, {"AIRISK_EVAL_HISTORY_PATH": str(tmp_path / "history" / "trust_gate_history.jsonl")}):
        with patch.object(run_eval_suite, "OUTPUT_ROOT", output_root):
            with patch.object(run_eval_suite, "_utc_now_iso", return_value="2026-01-22T00:00:00Z"):
                failures = run_eval_suite.write_summary(results, thresholds=thresholds, enforce_gates=True)

    assert failures == 0
    expansion_payload = json.loads((output_root / "expansion_gate.json").read_text(encoding="utf-8"))
    assert expansion_payload["status"] in {"open", "closed"}
    assert expansion_payload["required_consecutive_passes"] >= 1
    plugin_payload = json.loads((output_root / "plugin_conformance.json").read_text(encoding="utf-8"))
    assert plugin_payload["plugin_contract_version"] == "1"
    assert plugin_payload["status"] in {"passed", "failed"}
    promotion_payload = json.loads((output_root / "support_level_promotion.json").read_text(encoding="utf-8"))
    assert promotion_payload["status"] in {"ready", "blocked"}
    summary_md = (output_root / "summary.md").read_text(encoding="utf-8")
    assert "## Expansion Gate" in summary_md
    assert "## Plugin Conformance" in summary_md
    assert "## Support-Level Promotion" in summary_md
