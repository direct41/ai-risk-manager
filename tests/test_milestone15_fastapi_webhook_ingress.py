from __future__ import annotations

from pathlib import Path

from ai_risk_manager.collectors.plugins.registry import get_signal_plugin_for_stack
from ai_risk_manager.pipeline.run import run_pipeline
from ai_risk_manager.schemas.types import RunContext


def test_milestone15_fastapi_webhook_ingress_maps_webhook_family_and_keeps_coverage(tmp_path: Path) -> None:
    repo_path = Path(__file__).resolve().parents[1] / "eval" / "repos" / "milestone15_fastapi_webhook_ingress"
    out_dir = tmp_path / ".riskmap"

    plugin = get_signal_plugin_for_stack("fastapi_pytest")
    assert plugin is not None

    artifacts = plugin.collect(repo_path)
    signals = plugin.collect_signals_from_artifacts(artifacts)

    ingress_families = {
        str(signal.attributes.get("family", ""))
        for signal in signals.signals
        if signal.kind == "ingress_surface"
    }
    coverage_families = {
        str(signal.attributes.get("family", ""))
        for signal in signals.signals
        if signal.kind == "test_to_ingress_coverage"
    }

    assert "webhook" in ingress_families
    assert "webhook" in coverage_families

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
    assert "critical_path_no_tests" not in rule_ids
