from __future__ import annotations

from pathlib import Path

from ai_risk_manager.pipeline.run import run_pipeline
from ai_risk_manager.schemas.types import RunContext


def test_milestone13_express_html_gap_flags_unsafe_html_sink(tmp_path: Path) -> None:
    repo_path = Path(__file__).resolve().parents[1] / "eval" / "repos" / "milestone13_express_html_gap"
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
    assert result.summary.support_level_applied == "l2"

    rule_ids = {finding.rule_id for finding in result.findings.findings}
    assert "stored_xss_unsafe_innerhtml" in rule_ids


def test_milestone13_express_html_balanced_avoids_unsafe_html_sink(tmp_path: Path) -> None:
    repo_path = Path(__file__).resolve().parents[1] / "eval" / "repos" / "milestone13_express_html_balanced"
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
    assert result.summary.support_level_applied == "l2"

    rule_ids = {finding.rule_id for finding in result.findings.findings}
    assert "stored_xss_unsafe_innerhtml" not in rule_ids
