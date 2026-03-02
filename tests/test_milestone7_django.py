from __future__ import annotations

from pathlib import Path

from ai_risk_manager.pipeline.run import run_pipeline
from ai_risk_manager.schemas.types import RunContext


def test_milestone7_django_viewset_repo_has_no_critical_path_gap(tmp_path: Path) -> None:
    repo_path = Path(__file__).resolve().parents[1] / "eval" / "repos" / "milestone7_django_viewset"
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
    assert "critical_path_no_tests" not in rule_ids
    assert any(edge.type == "covered_by" for edge in result.graph.edges)
