from __future__ import annotations

from pathlib import Path

from ai_risk_manager.pipeline.run import run_pipeline
from ai_risk_manager.schemas.types import RunContext


def _run_repo(repo_name: str, tmp_path: Path):
    repo_path = Path(__file__).resolve().parents[1] / "eval" / "repos" / repo_name
    out_dir = tmp_path / ".riskmap" / repo_name
    ctx = RunContext(
        repo_path=repo_path,
        mode="full",
        base=None,
        output_dir=out_dir,
        provider="auto",
        no_llm=True,
    )
    return run_pipeline(ctx)


def test_balanced_repo_has_no_core_findings(tmp_path: Path) -> None:
    result, code, _ = _run_repo("milestone5_balanced", tmp_path)
    assert code == 0
    assert result is not None
    rule_ids = {f.rule_id for f in result.findings.findings}
    assert "critical_path_no_tests" not in rule_ids
    assert "missing_transition_handler" not in rule_ids


def test_missing_handler_repo_flags_transition_gap(tmp_path: Path) -> None:
    result, code, _ = _run_repo("milestone5_missing_handler", tmp_path)
    assert code == 0
    assert result is not None
    rule_ids = {f.rule_id for f in result.findings.findings}
    assert "missing_transition_handler" in rule_ids
