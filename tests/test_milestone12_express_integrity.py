from __future__ import annotations

from pathlib import Path

from ai_risk_manager.pipeline.run import run_pipeline
from ai_risk_manager.schemas.types import RunContext


def test_milestone12_express_integrity_gap_flags_stage11_p0_rules(tmp_path: Path) -> None:
    repo_path = Path(__file__).resolve().parents[1] / "eval" / "repos" / "milestone12_express_integrity_gap"
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
    assert "input_normalization_char_split" in rule_ids
    assert "response_field_contract_mismatch" in rule_ids
    assert "db_insert_binding_mismatch" in rule_ids
    assert "critical_write_scope_missing_entity_filter" in rule_ids
    assert "stale_write_without_conflict_guard" in rule_ids
    assert "session_token_key_mismatch" in rule_ids


def test_milestone12_express_integrity_balanced_avoids_stage11_p0_rules(tmp_path: Path) -> None:
    repo_path = Path(__file__).resolve().parents[1] / "eval" / "repos" / "milestone12_express_integrity_balanced"
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
    assert "input_normalization_char_split" not in rule_ids
    assert "response_field_contract_mismatch" not in rule_ids
    assert "db_insert_binding_mismatch" not in rule_ids
    assert "critical_write_scope_missing_entity_filter" not in rule_ids
    assert "stale_write_without_conflict_guard" not in rule_ids
    assert "session_token_key_mismatch" not in rule_ids
