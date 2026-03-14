from __future__ import annotations

from pathlib import Path

from ai_risk_manager.pipeline.run import run_pipeline
from ai_risk_manager.schemas.types import RunContext


def test_milestone14_express_ui_gap_flags_ui_ergonomics_rules(tmp_path: Path) -> None:
    repo_path = Path(__file__).resolve().parents[1] / "eval" / "repos" / "milestone14_express_ui_gap"
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
    assert "pagination_page_not_normalized" in rule_ids
    assert "save_button_partial_form_enabled" in rule_ids
    assert "mobile_layout_min_width_overflow" in rule_ids


def test_milestone14_express_ui_balanced_avoids_ui_ergonomics_rules(tmp_path: Path) -> None:
    repo_path = Path(__file__).resolve().parents[1] / "eval" / "repos" / "milestone14_express_ui_balanced"
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
    assert "pagination_page_not_normalized" not in rule_ids
    assert "save_button_partial_form_enabled" not in rule_ids
    assert "mobile_layout_min_width_overflow" not in rule_ids
