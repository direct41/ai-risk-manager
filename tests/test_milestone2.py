from __future__ import annotations

from pathlib import Path

from ai_risk_manager.pipeline.run import run_pipeline
from ai_risk_manager.schemas.types import RunContext


def test_milestone2_eval_repo_produces_two_rule_types(tmp_path: Path) -> None:
    repo_path = Path(__file__).resolve().parents[1] / "eval" / "repos" / "milestone2_fastapi"
    out_dir = tmp_path / ".riskmap"

    ctx = RunContext(
        repo_path=repo_path,
        mode="full",
        base=None,
        output_dir=out_dir,
        provider="auto",
        no_llm=True,
    )

    result, code, _ = run_pipeline(ctx)
    assert code == 0
    assert result is not None

    rule_ids = {f.rule_id for f in result.findings.findings}
    assert "critical_path_no_tests" in rule_ids
    assert "missing_transition_handler" in rule_ids


def test_milestone2_eval_repo_extracts_pydantic_and_transitions(tmp_path: Path) -> None:
    repo_path = Path(__file__).resolve().parents[1] / "eval" / "repos" / "milestone2_fastapi"
    out_dir = tmp_path / ".riskmap"

    ctx = RunContext(
        repo_path=repo_path,
        mode="full",
        base=None,
        output_dir=out_dir,
        provider="auto",
        no_llm=True,
    )

    result, code, _ = run_pipeline(ctx)
    assert code == 0
    assert result is not None

    entity_names = {n.name for n in result.graph.nodes if n.type == "Entity"}
    assert {"OrderCreate", "OrderOut"}.issubset(entity_names)

    assert result.graph.declared_transitions
    transition_pairs = {(t.source, t.target) for t in result.graph.declared_transitions}
    assert ("pending", "cancelled") in transition_pairs
