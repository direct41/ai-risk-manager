from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Literal

from ai_risk_manager import __version__
from ai_risk_manager.agents.provider import resolve_provider
from ai_risk_manager.agents.qa_strategy_agent import generate_test_plan
from ai_risk_manager.agents.semantic_risk_agent import generate_semantic_findings
from ai_risk_manager.collectors.plugins.base import ArtifactBundle
from ai_risk_manager.collectors.plugins.registry import get_plugin_for_stack
from ai_risk_manager.graph.builder import build_graph, low_confidence_ratio
from ai_risk_manager.pipeline.merge_findings import ensure_fingerprint, merge_findings
from ai_risk_manager.reports.generator import render_pr_summary_md, render_report_md, write_report
from ai_risk_manager.rules.engine import run_rules
from ai_risk_manager.rules.suppressions import apply_suppressions, load_suppressions
from ai_risk_manager.schemas.types import (
    AnalysisScope,
    AppliedSupportLevel,
    CIMode,
    CompetitiveMode,
    FindingsReport,
    Graph,
    PipelineResult,
    PreflightResult,
    RunContext,
    RunMetrics,
    RunSummary,
    to_dict,
    write_json,
)
from ai_risk_manager.stacks.discovery import detect_stack

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}
CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}
RISK_POLICY_TOP_LIMIT = {"conservative": 10, "balanced": 20, "aggressive": 30}
CI_MODE_MATRIX: dict[AppliedSupportLevel, dict[CIMode, CIMode]] = {
    "l0": {
        "advisory": "advisory",
        "soft": "advisory",
        "block_new_critical": "advisory",
    },
    "l1": {
        "advisory": "advisory",
        "soft": "soft",
        "block_new_critical": "soft",
    },
    "l2": {
        "advisory": "advisory",
        "soft": "soft",
        "block_new_critical": "block_new_critical",
    },
}


def _resolve_support_level(requested: str, detected_stack: str) -> AppliedSupportLevel:
    if requested in {"l0", "l1", "l2"}:
        return requested
    if detected_stack == "unknown":
        return "l0"
    return "l2"


def _resolve_competitive_mode(analysis_engine: str) -> CompetitiveMode:
    if analysis_engine == "deterministic":
        return "deterministic"
    return "hybrid"


def _resolve_effective_ci_mode(requested: CIMode, support_level_applied: AppliedSupportLevel) -> tuple[CIMode, str | None]:
    effective = CI_MODE_MATRIX[support_level_applied][requested]
    if effective == requested:
        return effective, None
    if support_level_applied == "l0":
        return effective, f"ci_mode overridden to advisory for support_level=l0 (requested: {requested})."
    if support_level_applied == "l1":
        return effective, f"ci_mode downgraded to soft for support_level=l1 (requested: {requested})."
    return effective, None


def _progress(step: int, total: int, label: str, start_ts: float | None = None) -> float:
    if start_ts is None:
        print(f"[{step}/{total}] {label} ...", flush=True)
        return time.perf_counter()
    elapsed = time.perf_counter() - start_ts
    print(f"[{step}/{total}] {label} ... done ({elapsed:.1f}s)", flush=True)
    return elapsed


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def _source_file_ref(source_ref: str) -> str:
    normalized = _normalize_path(source_ref)
    parts = normalized.rsplit(":", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return normalized


def _baseline_graph_is_valid(path: Path | None) -> bool:
    if not path or not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and isinstance(payload.get("nodes"), list)


def _load_baseline_fingerprints(baseline_graph: Path | None) -> tuple[set[str] | None, str | None]:
    if not baseline_graph:
        return None, "baseline_graph_missing"

    findings_file = baseline_graph.parent / "findings.json"
    if not findings_file.is_file():
        return None, "baseline_findings_missing"

    try:
        payload = json.loads(findings_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "baseline_findings_invalid"

    rows = payload.get("findings")
    if not isinstance(rows, list):
        return None, "baseline_findings_invalid"

    fingerprints: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        fp = row.get("fingerprint")
        if isinstance(fp, str) and fp:
            fingerprints.add(fp)
            continue
        base = "|".join(
            [
                str(row.get("rule_id", "")),
                _source_file_ref(str(row.get("source_ref", ""))),
                str(row.get("title", "")).strip().lower(),
                str(row.get("origin", "deterministic")),
            ]
        )
        fingerprints.add(hashlib.sha1(base.encode("utf-8")).hexdigest()[:16])
    return fingerprints, None


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

    impacted_ids = {node.id for node in graph.nodes if _source_file_ref(node.source_ref) in changed}
    if not impacted_ids:
        return Graph(nodes=[], edges=[], declared_transitions=[], handled_transitions=[])

    expanded = set(impacted_ids)
    for edge in graph.edges:
        if edge.source_node_id in impacted_ids or edge.target_node_id in impacted_ids:
            expanded.add(edge.source_node_id)
            expanded.add(edge.target_node_id)

    nodes = [node_by_id[node_id] for node_id in expanded if node_id in node_by_id]
    edges = [edge for edge in graph.edges if edge.source_node_id in expanded and edge.target_node_id in expanded]
    declared = [transition for transition in graph.declared_transitions if _source_file_ref(transition.source_ref) in changed]
    handled = [transition for transition in graph.handled_transitions if _source_file_ref(transition.source_ref) in changed]
    return Graph(nodes=nodes, edges=edges, declared_transitions=declared, handled_transitions=handled)


def _with_metadata(payload: dict, generated_at: str) -> dict:
    return {
        **payload,
        "schema_version": "1.1",
        "generated_at": generated_at,
        "tool_version": __version__,
    }


def _max_severity(findings_count: list[str]) -> str | None:
    if not findings_count:
        return None
    return max(findings_count, key=lambda severity: SEVERITY_RANK.get(severity, 0))


def _apply_baseline_status(
    findings: FindingsReport,
    *,
    mode: Literal["full", "pr"],
    baseline_fingerprints: set[str] | None,
    fallback_reason: str | None,
) -> tuple[FindingsReport, RunSummary]:
    if mode != "pr":
        unchanged = [ensure_fingerprint(finding) for finding in findings.findings]
        for finding in unchanged:
            finding.status = "unchanged"
        return FindingsReport(findings=unchanged, generated_without_llm=findings.generated_without_llm), RunSummary(
            new_count=0,
            resolved_count=0,
            unchanged_count=len(unchanged),
            fallback_reason=fallback_reason,
        )

    normalized = [ensure_fingerprint(finding) for finding in findings.findings]
    current_fps = {finding.fingerprint for finding in normalized}
    if baseline_fingerprints is None:
        for finding in normalized:
            finding.status = "new"
        return FindingsReport(findings=normalized, generated_without_llm=findings.generated_without_llm), RunSummary(
            new_count=len(normalized),
            resolved_count=0,
            unchanged_count=0,
            fallback_reason=fallback_reason or "baseline_findings_missing",
        )

    for finding in normalized:
        finding.status = "unchanged" if finding.fingerprint in baseline_fingerprints else "new"

    new_count = sum(1 for finding in normalized if finding.status == "new")
    unchanged_count = len(normalized) - new_count
    resolved_count = len(baseline_fingerprints - current_fps)
    return FindingsReport(findings=normalized, generated_without_llm=findings.generated_without_llm), RunSummary(
        new_count=new_count,
        resolved_count=resolved_count,
        unchanged_count=unchanged_count,
        fallback_reason=fallback_reason,
    )


def _resolve_ref_path_line(repo_path: Path, source_ref: str) -> tuple[Path, int | None]:
    line_no: int | None = None
    ref = source_ref.strip()
    parts = ref.rsplit(":", 1)
    if len(parts) == 2 and parts[1].isdigit():
        ref = parts[0]
        line_no = int(parts[1])
    path = Path(ref)
    if not path.is_absolute():
        path = repo_path / path
    return path, line_no


def _ref_exists(repo_path: Path, source_ref: str) -> bool:
    path, line_no = _resolve_ref_path_line(repo_path, source_ref)
    if not path.is_file():
        return False
    if line_no is None:
        return True
    try:
        with path.open("r", encoding="utf-8") as fh:
            for idx, _ in enumerate(fh, start=1):
                if idx == line_no:
                    return True
    except OSError:
        return False
    return False


def _verification_stats(
    findings: FindingsReport,
    repo_path: Path,
) -> tuple[float, float, set[str]]:
    if not findings.findings:
        return 1.0, 1.0, set()

    total = len(findings.findings)
    with_evidence = 0
    verified_fingerprints: set[str] = set()
    for finding in findings.findings:
        refs = [ref for ref in finding.evidence_refs if ref]
        if refs:
            with_evidence += 1
        if any(_ref_exists(repo_path, ref) for ref in refs):
            verified_fingerprints.add(finding.fingerprint)

    return (
        len(verified_fingerprints) / total,
        with_evidence / total,
        verified_fingerprints,
    )


def _compute_run_metrics(
    findings: FindingsReport,
    summary: RunSummary,
    *,
    support_level_applied: AppliedSupportLevel,
    competitive_mode: CompetitiveMode,
    verification_pass_rate: float,
    evidence_completeness: float,
    analysis_scope: AnalysisScope,
    duration_ms: int,
) -> RunMetrics:
    total = max(1, len(findings.findings))
    supported = [
        finding
        for finding in findings.findings
        if finding.evidence_refs and CONFIDENCE_RANK.get(finding.confidence, 0) >= CONFIDENCE_RANK["medium"]
    ]
    actionable = [
        finding for finding in findings.findings if finding.evidence_refs and bool(finding.recommendation.strip())
    ]
    triage_time_proxy_min = float(max(1, len(findings.findings) * 2))
    return RunMetrics(
        precision_proxy=len(supported) / total,
        fallback_reason=summary.fallback_reason,
        new_findings_count=summary.new_count,
        actionability_proxy=len(actionable) / total,
        triage_time_proxy_min=triage_time_proxy_min,
        verification_pass_rate=verification_pass_rate,
        evidence_completeness=evidence_completeness,
        support_level_applied=support_level_applied,
        competitive_mode=competitive_mode,
        analysis_scope=analysis_scope,
        duration_ms=duration_ms,
    )


def run_pipeline(ctx: RunContext) -> tuple[PipelineResult | None, int, list[str]]:
    pipeline_started = time.perf_counter()
    total_steps = 6
    notes: list[str] = []
    fallback_reason: str | None = None

    t = _progress(1, total_steps, "Stack detection and pre-flight")
    detection = detect_stack(ctx.repo_path)
    notes.append(f"Detected stack: {detection.stack_id} (confidence: {detection.confidence}).")
    support_level_applied = _resolve_support_level(ctx.support_level, detection.stack_id)
    competitive_mode = _resolve_competitive_mode(ctx.analysis_engine)
    notes.append(f"Support level applied: {support_level_applied}.")
    if ctx.risk_policy != "balanced":
        notes.append(f"Risk policy: {ctx.risk_policy}.")

    plugin = get_plugin_for_stack(detection.stack_id)
    if plugin is None and support_level_applied != "l0":
        _progress(1, total_steps, "Stack detection and pre-flight", t)
        notes.extend(detection.reasons)
        notes.append(f"No collector plugin is registered for stack '{detection.stack_id}'.")
        return None, 2, notes

    if plugin is None:
        preflight = PreflightResult(
            status="WARN",
            reasons=[*detection.reasons, "Unknown stack: fallback to L0 generic advisory mode."],
        )
    else:
        preflight = plugin.preflight(ctx.repo_path, probe_data=detection.probe_data)
    _progress(1, total_steps, "Stack detection and pre-flight", t)

    if preflight.status == "FAIL":
        notes.extend(preflight.reasons)
        return None, 2, notes
    if preflight.status == "WARN":
        notes.extend(preflight.reasons)

    t = _progress(2, total_steps, "Collecting artifacts")
    if plugin is None:
        artifacts = ArtifactBundle()
    else:
        artifacts = plugin.collect(ctx.repo_path)
    _progress(2, total_steps, "Collecting artifacts", t)

    t = _progress(3, total_steps, "Building graph")
    graph = build_graph(artifacts)
    _progress(3, total_steps, "Building graph", t)

    analysis_scope: AnalysisScope = "full"
    analysis_graph = graph
    if ctx.mode == "pr":
        if _baseline_graph_is_valid(ctx.baseline_graph):
            changed_files = _resolve_changed_files(ctx.repo_path, ctx.base)
            if changed_files is None:
                analysis_scope = "full_fallback"
                fallback_reason = "changed_files_unresolved"
                notes.append("Could not resolve changed files; using full_fallback scan.")
            elif not changed_files:
                analysis_scope = "full_fallback"
                fallback_reason = "changed_files_empty"
                notes.append("No changed files detected in PR diff; using full_fallback scan.")
            else:
                impacted_graph = _filter_graph_to_impacted(graph, changed_files)
                if impacted_graph.nodes:
                    analysis_graph = impacted_graph
                    analysis_scope = "impacted"
                    notes.append(f"Impacted subgraph selected from {len(changed_files)} changed file(s).")
                else:
                    analysis_scope = "full_fallback"
                    fallback_reason = "changed_files_not_mapped"
                    notes.append("Changed files did not map to graph nodes; using full_fallback scan.")
        else:
            analysis_scope = "full_fallback"
            fallback_reason = "baseline_graph_missing_or_invalid"
            notes.append("Baseline graph not found or invalid; using full_fallback scan.")

    t = _progress(4, total_steps, "Running deterministic rules")
    findings_raw = run_rules(analysis_graph, risk_policy=ctx.risk_policy)
    _progress(4, total_steps, "Running deterministic rules", t)

    suppress_path = ctx.suppress_file
    if suppress_path is None:
        default = ctx.repo_path / ".airiskignore"
        suppress_path = default if default.is_file() else None
    suppressions, suppression_notes = load_suppressions(suppress_path)
    notes.extend(suppression_notes)
    findings_raw, suppressed_count = apply_suppressions(findings_raw, suppressions)
    if suppressed_count:
        notes.append(f"Suppressed findings: {suppressed_count}.")

    ci = bool(os.getenv("CI") or os.getenv("GITHUB_ACTIONS"))
    force_no_llm = ctx.no_llm or ctx.analysis_engine == "deterministic"
    provider_resolution = resolve_provider(ctx.provider, no_llm=force_no_llm, ci=ci)
    notes.extend(provider_resolution.notes)
    if not force_no_llm and ctx.provider in {"api", "cli"} and provider_resolution.provider == "none":
        return None, 1, notes

    t = _progress(5, total_steps, "Semantic AI risk stage")
    semantic_findings = FindingsReport(findings=[], generated_without_llm=True)
    if ctx.analysis_engine != "deterministic":
        semantic_findings, semantic_notes = generate_semantic_findings(
            analysis_graph,
            provider=provider_resolution.provider,
            generated_without_llm=provider_resolution.generated_without_llm,
        )
        notes.extend(semantic_notes)
    else:
        notes.append("analysis_engine=deterministic: semantic AI stage skipped.")
    _progress(5, total_steps, "Semantic AI risk stage", t)

    top_limit = RISK_POLICY_TOP_LIMIT[ctx.risk_policy]
    merged_findings = merge_findings(
        findings_raw,
        (
            semantic_findings
            if ctx.analysis_engine in {"hybrid", "ai_first"}
            else FindingsReport(findings=[], generated_without_llm=True)
        ),
        min_confidence=ctx.min_confidence,
        top_limit=top_limit,
    )
    merged_findings, suppressed_after_merge = apply_suppressions(merged_findings, suppressions)
    if suppressed_after_merge:
        suppressed_count += suppressed_after_merge
        notes.append(f"Suppressed merged findings: {suppressed_after_merge}.")

    baseline_fingerprints: set[str] | None = None
    if ctx.mode == "pr":
        baseline_fingerprints, baseline_reason = _load_baseline_fingerprints(ctx.baseline_graph)
        if baseline_reason:
            fallback_reason = fallback_reason or baseline_reason
            notes.append(f"Baseline findings note: {baseline_reason}.")

    findings, summary = _apply_baseline_status(
        merged_findings,
        mode=ctx.mode,
        baseline_fingerprints=baseline_fingerprints,
        fallback_reason=fallback_reason,
    )
    verification_pass_rate, evidence_completeness, verified_fingerprints = _verification_stats(findings, ctx.repo_path)
    summary.support_level_applied = support_level_applied
    summary.verification_pass_rate = verification_pass_rate
    summary.evidence_completeness = evidence_completeness
    summary.competitive_mode = competitive_mode

    t = _progress(6, total_steps, "QA strategy agent")
    test_plan = generate_test_plan(
        findings,
        analysis_graph,
        provider=provider_resolution.provider,
        generated_without_llm=provider_resolution.generated_without_llm or ctx.analysis_engine == "deterministic",
    )
    _progress(6, total_steps, "QA strategy agent", t)

    duration_ms = int((time.perf_counter() - pipeline_started) * 1000)
    run_metrics = _compute_run_metrics(
        findings,
        summary,
        support_level_applied=support_level_applied,
        competitive_mode=competitive_mode,
        verification_pass_rate=verification_pass_rate,
        evidence_completeness=evidence_completeness,
        analysis_scope=analysis_scope,
        duration_ms=duration_ms,
    )

    result = PipelineResult(
        preflight=preflight,
        analysis_scope=analysis_scope,
        data_quality_low_confidence_ratio=low_confidence_ratio(analysis_graph),
        suppressed_count=suppressed_count,
        graph=analysis_graph,
        findings_raw=findings_raw,
        findings=findings,
        test_plan=test_plan,
        summary=summary,
        run_metrics=run_metrics,
    )

    ctx.output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if ctx.output_format in {"json", "both"}:
        write_json(ctx.output_dir / "graph.json", _with_metadata(to_dict(analysis_graph), generated_at))
        if analysis_scope != "full":
            notes.append("graph.json contains analysis graph for current scope (not full repository graph).")
        write_json(ctx.output_dir / "findings.raw.json", _with_metadata(to_dict(findings_raw), generated_at))
        write_json(ctx.output_dir / "findings.json", _with_metadata(to_dict(findings), generated_at))
        write_json(ctx.output_dir / "test_plan.json", _with_metadata(to_dict(test_plan), generated_at))
        write_json(ctx.output_dir / "run_metrics.json", _with_metadata(to_dict(run_metrics), generated_at))

    if ctx.output_format in {"md", "both"}:
        report = render_report_md(result, notes)
        write_report(ctx.output_dir / "report.md", report)
        if ctx.mode == "pr":
            pr_summary = render_pr_summary_md(result, notes, only_new=ctx.only_new)
            write_report(ctx.output_dir / "pr_summary.md", pr_summary)

    exit_code = 0
    if ctx.fail_on_severity:
        max_sev = _max_severity([finding.severity for finding in result.findings.findings])
        if max_sev and SEVERITY_RANK[max_sev] >= SEVERITY_RANK[ctx.fail_on_severity]:
            notes.append(
                f"Fail-on-severity triggered: found '{max_sev}' which is >= threshold '{ctx.fail_on_severity}'."
            )
            exit_code = 3

    effective_ci_mode, ci_mode_note = _resolve_effective_ci_mode(ctx.ci_mode, support_level_applied)
    if ci_mode_note:
        notes.append(ci_mode_note)

    if effective_ci_mode == "soft":
        if any(
            finding.status == "new" and SEVERITY_RANK[finding.severity] >= SEVERITY_RANK["high"]
            for finding in result.findings.findings
        ):
            notes.append("ci_mode=soft triggered: new high/critical finding exists.")
            exit_code = 3
    elif effective_ci_mode == "block_new_critical":
        if any(
            finding.status == "new"
            and finding.severity == "critical"
            and finding.fingerprint in verified_fingerprints
            for finding in result.findings.findings
        ):
            notes.append("ci_mode=block_new_critical triggered: verified new critical finding exists.")
            exit_code = 3

    return result, exit_code, notes
