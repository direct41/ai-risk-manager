from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_mutation_score.py"
SPEC = importlib.util.spec_from_file_location("check_mutation_score", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
check_mutation_score = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = check_mutation_score
SPEC.loader.exec_module(check_mutation_score)


def _stats(**overrides: int) -> dict[str, int]:
    payload = {
        "killed": 75,
        "survived": 25,
        "total": 100,
        "no_tests": 0,
        "skipped": 0,
        "suspicious": 0,
        "timeout": 0,
        "check_was_interrupted_by_user": 0,
        "segfault": 0,
    }
    payload.update(overrides)
    return payload


def test_mutation_gate_accepts_exact_threshold() -> None:
    score, errors = check_mutation_score.evaluate_stats(_stats(), 0.75)

    assert score == 0.75
    assert errors == []


def test_mutation_gate_rejects_low_score_and_bad_run_status() -> None:
    score, errors = check_mutation_score.evaluate_stats(
        _stats(killed=74, survived=25, timeout=1),
        0.75,
    )

    assert score == 0.74
    assert any("below required threshold" in error for error in errors)
    assert "mutation run has 1 timeout mutant(s)" in errors


def test_mutation_gate_rejects_inconsistent_or_malformed_stats() -> None:
    score, errors = check_mutation_score.evaluate_stats(_stats(total=101), 0.75)
    assert score is None
    assert any("do not account" in error for error in errors)

    score, errors = check_mutation_score.evaluate_stats({"killed": True}, 0.75)
    assert score is None
    assert errors


def test_mutation_gate_cli_reports_pass_and_failure(tmp_path: Path, capsys) -> None:
    path = tmp_path / "stats.json"
    path.write_text(json.dumps(_stats()), encoding="utf-8")

    assert check_mutation_score.main([str(path)]) == 0
    assert "75/100 killed (75.00%)" in capsys.readouterr().out

    path.write_text("not-json", encoding="utf-8")
    assert check_mutation_score.main([str(path)]) == 2
    assert "unable to read mutation stats" in capsys.readouterr().out
