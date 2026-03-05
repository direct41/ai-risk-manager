from __future__ import annotations

from pathlib import Path

from ai_risk_manager.pipeline.run import run_pipeline
from ai_risk_manager.schemas.types import RunContext


def test_milestone10_express_authz_gap_flags_missing_authz_and_tests(tmp_path: Path) -> None:
    repo_path = Path(__file__).resolve().parents[1] / "eval" / "repos" / "milestone10_express_authz_gap"
    out_dir = tmp_path / ".riskmap"

    ctx = RunContext(
        repo_path=repo_path,
        mode="full",
        base=None,
        output_dir=out_dir,
        provider="auto",
        no_llm=True,
        support_level="auto",
    )

    result, code, _ = run_pipeline(ctx)
    assert code == 0
    assert result is not None
    assert result.summary.support_level_applied == "l1"

    rule_ids = {finding.rule_id for finding in result.findings.findings}
    assert "critical_path_no_tests" in rule_ids
    assert "critical_write_missing_authz" in rule_ids
