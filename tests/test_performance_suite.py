from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_performance_suite.py"
SPEC = importlib.util.spec_from_file_location("run_performance_suite", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
performance_suite = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = performance_suite
SPEC.loader.exec_module(performance_suite)


def test_percentile_uses_nearest_rank() -> None:
    values = [50.0, 10.0, 30.0, 20.0, 40.0]

    assert performance_suite._percentile(values, 0.50) == 30.0
    assert performance_suite._percentile(values, 0.95) == 50.0

    with pytest.raises(ValueError, match="at least one sample"):
        performance_suite._percentile([], 0.50)


def test_evaluate_budgets_reports_latency_memory_and_missing_workload() -> None:
    report = {
        "workloads": {
            "small": {"latency_ms": {"p95": 2100.0}, "peak_rss_mb": 300.0},
        }
    }
    budgets = {
        "workloads": {
            "small": {"p95_latency_ms": 2000.0, "peak_rss_mb": 256.0},
            "large": {"p95_latency_ms": 20000.0, "peak_rss_mb": 768.0},
        }
    }

    errors = performance_suite.evaluate_budgets(report, budgets)

    assert any("small p95 latency" in error for error in errors)
    assert any("small peak RSS" in error for error in errors)
    assert "missing workload result: large" in errors


def test_workloads_match_versioned_budget_file() -> None:
    budgets = performance_suite._load_budgets(performance_suite.DEFAULT_BUDGETS)

    assert {workload.name for workload in performance_suite.WORKLOADS} == set(budgets["workloads"])
    for workload in performance_suite.WORKLOADS:
        assert workload.file_count == budgets["workloads"][workload.name]["file_count"]
