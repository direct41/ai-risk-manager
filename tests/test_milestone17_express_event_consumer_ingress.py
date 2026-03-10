from __future__ import annotations

from pathlib import Path

from ai_risk_manager.collectors.plugins.registry import get_signal_plugin_for_stack
from ai_risk_manager.pipeline.run import run_pipeline
from ai_risk_manager.schemas.types import RunContext


def test_milestone17_express_event_consumer_ingress_maps_event_family(tmp_path: Path) -> None:
    repo_path = Path(__file__).resolve().parents[1] / "eval" / "repos" / "milestone17_express_event_consumer_ingress"
    out_dir = tmp_path / ".riskmap"

    plugin = get_signal_plugin_for_stack("express_node")
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

    assert "event_consumer" in ingress_families
    assert "event_consumer" in coverage_families

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
    rule_ids = {finding.rule_id for finding in result.findings.findings}
    assert "critical_path_no_tests" not in rule_ids
