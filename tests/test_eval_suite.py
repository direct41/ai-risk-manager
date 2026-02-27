from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


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
