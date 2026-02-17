from __future__ import annotations

from pathlib import Path
import os
import time
from typing import Literal

from ai_risk_manager.agents.provider import resolve_provider
from ai_risk_manager.agents.qa_strategy_agent import generate_test_plan
from ai_risk_manager.agents.risk_agent import generate_findings
from ai_risk_manager.collectors.collector import collect_artifacts, preflight_check
from ai_risk_manager.graph.builder import build_graph, low_confidence_ratio
from ai_risk_manager.reports.generator import render_pr_summary_md, render_report_md, write_report
from ai_risk_manager.rules.engine import run_rules
from ai_risk_manager.schemas.types import PipelineResult, RunContext, to_dict, write_json


def _progress(step: int, total: int, label: str, start_ts: float | None = None) -> float:
    if start_ts is None:
        print(f"[{step}/{total}] {label} ...", flush=True)
        return time.perf_counter()
    elapsed = time.perf_counter() - start_ts
    print(f"[{step}/{total}] {label} ... done ({elapsed:.1f}s)", flush=True)
    return elapsed


def run_pipeline(ctx: RunContext) -> tuple[PipelineResult | None, int, list[str]]:
    total_steps = 6
    notes: list[str] = []

    t = _progress(1, total_steps, "Pre-flight check")
    preflight = preflight_check(ctx.repo_path)
    _progress(1, total_steps, "Pre-flight check", t)

    if preflight.status == "FAIL":
        notes.extend(preflight.reasons)
        return None, 2, notes

    t = _progress(2, total_steps, "Collecting artifacts")
    artifacts = collect_artifacts(ctx.repo_path)
    _progress(2, total_steps, "Collecting artifacts", t)

    t = _progress(3, total_steps, "Building graph")
    graph = build_graph(artifacts)
    _progress(3, total_steps, "Building graph", t)

    t = _progress(4, total_steps, "Running rules")
    findings_raw = run_rules(graph)
    _progress(4, total_steps, "Running rules", t)

    ci = bool(os.getenv("CI") or os.getenv("GITHUB_ACTIONS"))
    provider_resolution = resolve_provider(ctx.provider, no_llm=ctx.no_llm, ci=ci)
    notes.extend(provider_resolution.notes)
    if not ctx.no_llm and ctx.provider in {"api", "cli"} and provider_resolution.provider == "none":
        return None, 1, notes

    t = _progress(5, total_steps, "Risk agent")
    findings = generate_findings(
        findings_raw,
        graph,
        provider=provider_resolution.provider,
        generated_without_llm=provider_resolution.generated_without_llm,
    )
    _progress(5, total_steps, "Risk agent", t)

    t = _progress(6, total_steps, "QA strategy agent")
    test_plan = generate_test_plan(
        findings,
        graph,
        provider=provider_resolution.provider,
        generated_without_llm=provider_resolution.generated_without_llm,
    )
    _progress(6, total_steps, "QA strategy agent", t)

    if ctx.mode == "pr":
        if ctx.baseline_graph and ctx.baseline_graph.is_file() and ctx.baseline_graph.stat().st_size > 0:
            analysis_scope: Literal["impacted", "full", "full_fallback"] = "full"
            notes.append(
                f"Baseline graph found at {ctx.baseline_graph}, but impacted filtering is not implemented yet; "
                "using full scan."
            )
        else:
            analysis_scope = "full_fallback"
            notes.append("Baseline graph not found; using full_fallback scan.")
    else:
        analysis_scope = "full"
    result = PipelineResult(
        preflight=preflight,
        analysis_scope=analysis_scope,
        data_quality_low_confidence_ratio=low_confidence_ratio(graph),
        graph=graph,
        findings_raw=findings_raw,
        findings=findings,
        test_plan=test_plan,
    )

    ctx.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(ctx.output_dir / "graph.json", to_dict(graph))
    write_json(ctx.output_dir / "findings.raw.json", to_dict(findings_raw))
    write_json(ctx.output_dir / "findings.json", to_dict(findings))
    write_json(ctx.output_dir / "test_plan.json", to_dict(test_plan))

    report = render_report_md(result, notes)
    write_report(ctx.output_dir / "report.md", report)
    if ctx.mode == "pr":
        pr_summary = render_pr_summary_md(result, notes)
        write_report(ctx.output_dir / "pr_summary.md", pr_summary)

    return result, 0, notes
