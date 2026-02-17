from __future__ import annotations

import json
from pathlib import Path
import os
import subprocess
import time
from typing import Literal

from ai_risk_manager.agents.provider import resolve_provider
from ai_risk_manager.agents.qa_strategy_agent import generate_test_plan
from ai_risk_manager.agents.risk_agent import generate_findings
from ai_risk_manager.collectors.collector import collect_artifacts, preflight_check
from ai_risk_manager.graph.builder import build_graph, low_confidence_ratio
from ai_risk_manager.reports.generator import render_pr_summary_md, render_report_md, write_report
from ai_risk_manager.rules.engine import run_rules
from ai_risk_manager.schemas.types import Graph, PipelineResult, RunContext, to_dict, write_json


def _progress(step: int, total: int, label: str, start_ts: float | None = None) -> float:
    if start_ts is None:
        print(f"[{step}/{total}] {label} ...", flush=True)
        return time.perf_counter()
    elapsed = time.perf_counter() - start_ts
    print(f"[{step}/{total}] {label} ... done ({elapsed:.1f}s)", flush=True)
    return elapsed


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def _baseline_graph_is_valid(path: Path | None) -> bool:
    if not path or not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and isinstance(payload.get("nodes"), list)


def _resolve_changed_files(repo_path: Path, base: str | None) -> set[str] | None:
    env_override = os.getenv("AIRISK_CHANGED_FILES", "").strip()
    if env_override:
        return {_normalize_path(part.strip()) for part in env_override.split(",") if part.strip()}

    if not base:
        return None

    candidate_refs = [f"{base}...HEAD", f"origin/{base}...HEAD"]
    for ref in candidate_refs:
        try:
            proc = subprocess.run(
                ["git", "-C", str(repo_path), "diff", "--name-only", "--diff-filter=ACMRTUXB", ref],
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode == 0:
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            return {_normalize_path(line) for line in lines}
    return None


def _filter_graph_to_impacted(graph: Graph, changed_files: set[str]) -> Graph:
    changed = {_normalize_path(path) for path in changed_files}
    node_by_id = {node.id: node for node in graph.nodes}

    impacted_ids = {node.id for node in graph.nodes if _normalize_path(node.source_ref) in changed}
    if not impacted_ids:
        return Graph(nodes=[], edges=[], declared_transitions=[], handled_transitions=[])

    expanded = set(impacted_ids)
    for edge in graph.edges:
        if edge.source_node_id in impacted_ids or edge.target_node_id in impacted_ids:
            expanded.add(edge.source_node_id)
            expanded.add(edge.target_node_id)

    nodes = [node_by_id[node_id] for node_id in expanded if node_id in node_by_id]
    edges = [edge for edge in graph.edges if edge.source_node_id in expanded and edge.target_node_id in expanded]
    declared = [transition for transition in graph.declared_transitions if _normalize_path(transition.source_ref) in changed]
    handled = [transition for transition in graph.handled_transitions if _normalize_path(transition.source_ref) in changed]
    return Graph(nodes=nodes, edges=edges, declared_transitions=declared, handled_transitions=handled)


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

    analysis_scope: Literal["impacted", "full", "full_fallback"] = "full"
    analysis_graph = graph
    if ctx.mode == "pr":
        if _baseline_graph_is_valid(ctx.baseline_graph):
            changed_files = _resolve_changed_files(ctx.repo_path, ctx.base)
            if changed_files is None:
                analysis_scope = "full_fallback"
                notes.append("Could not resolve changed files; using full_fallback scan.")
            elif not changed_files:
                analysis_scope = "full_fallback"
                notes.append("No changed files detected in PR diff; using full_fallback scan.")
            else:
                impacted_graph = _filter_graph_to_impacted(graph, changed_files)
                if impacted_graph.nodes:
                    analysis_graph = impacted_graph
                    analysis_scope = "impacted"
                    notes.append(f"Impacted subgraph selected from {len(changed_files)} changed file(s).")
                else:
                    analysis_scope = "full_fallback"
                    notes.append("Changed files did not map to graph nodes; using full_fallback scan.")
        else:
            analysis_scope = "full_fallback"
            notes.append("Baseline graph not found or invalid; using full_fallback scan.")

    t = _progress(4, total_steps, "Running rules")
    findings_raw = run_rules(analysis_graph)
    _progress(4, total_steps, "Running rules", t)

    ci = bool(os.getenv("CI") or os.getenv("GITHUB_ACTIONS"))
    provider_resolution = resolve_provider(ctx.provider, no_llm=ctx.no_llm, ci=ci)
    notes.extend(provider_resolution.notes)
    if not ctx.no_llm and ctx.provider in {"api", "cli"} and provider_resolution.provider == "none":
        return None, 1, notes

    t = _progress(5, total_steps, "Risk agent")
    findings = generate_findings(
        findings_raw,
        analysis_graph,
        provider=provider_resolution.provider,
        generated_without_llm=provider_resolution.generated_without_llm,
    )
    _progress(5, total_steps, "Risk agent", t)

    t = _progress(6, total_steps, "QA strategy agent")
    test_plan = generate_test_plan(
        findings,
        analysis_graph,
        provider=provider_resolution.provider,
        generated_without_llm=provider_resolution.generated_without_llm,
    )
    _progress(6, total_steps, "QA strategy agent", t)

    result = PipelineResult(
        preflight=preflight,
        analysis_scope=analysis_scope,
        data_quality_low_confidence_ratio=low_confidence_ratio(analysis_graph),
        graph=analysis_graph,
        findings_raw=findings_raw,
        findings=findings,
        test_plan=test_plan,
    )

    ctx.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(ctx.output_dir / "graph.json", to_dict(analysis_graph))
    if analysis_scope != "full":
        notes.append("graph.json contains analysis graph for current scope (not full repository graph).")
    write_json(ctx.output_dir / "findings.raw.json", to_dict(findings_raw))
    write_json(ctx.output_dir / "findings.json", to_dict(findings))
    write_json(ctx.output_dir / "test_plan.json", to_dict(test_plan))

    report = render_report_md(result, notes)
    write_report(ctx.output_dir / "report.md", report)
    if ctx.mode == "pr":
        pr_summary = render_pr_summary_md(result, notes)
        write_report(ctx.output_dir / "pr_summary.md", pr_summary)

    return result, 0, notes
