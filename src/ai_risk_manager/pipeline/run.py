from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import time
from typing import Literal

from ai_risk_manager.agents.provider import ProviderResolution, resolve_provider
from ai_risk_manager.agents.qa_strategy_agent import generate_test_plan
from ai_risk_manager.agents.semantic_risk_agent import generate_semantic_findings
from ai_risk_manager.agents.semantic_signal_agent import generate_semantic_signals
from ai_risk_manager.collectors.plugins.base import ArtifactBundle, CollectorPlugin
from ai_risk_manager.collectors.plugins.registry import get_plugin_for_stack
from ai_risk_manager.graph.builder import build_graph, low_confidence_ratio
from ai_risk_manager.pipeline.merge_findings import ensure_fingerprint, merge_findings
from ai_risk_manager.pipeline.sinks import PipelineSinks
from ai_risk_manager.rules.engine import run_rules
from ai_risk_manager.rules.policy import PolicyConfig, apply_policy, is_blocking_enabled_for_finding, load_policy
from ai_risk_manager.rules.suppressions import apply_suppressions, load_suppressions
from ai_risk_manager.signals.adapters import artifact_bundle_to_signal_bundle
from ai_risk_manager.signals.merge import merge_signal_bundles
from ai_risk_manager.signals.types import SignalBundle
from ai_risk_manager.schemas.types import (
    AnalysisScope,
    AppliedSupportLevel,
    CIMode,
    CompetitiveMode,
    FindingsReport,
    GraphMode,
    Graph,
    PipelineResult,
    PreflightResult,
    RunContext,
    RunMetrics,
    RunSummary,
    TestPlan,
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
DEFAULT_SUPPORT_LEVEL_BY_STACK: dict[str, AppliedSupportLevel] = {
    "fastapi_pytest": "l2",
    "django_drf": "l2",
    "unknown": "l0",
}
_SUPPORT_LEVEL_DOWNGRADE: dict[AppliedSupportLevel, AppliedSupportLevel] = {
    "l2": "l1",
    "l1": "l0",
    "l0": "l0",
}


def _resolve_support_level(requested: str, detected_stack: str) -> AppliedSupportLevel:
    if requested in {"l0", "l1", "l2"}:
        return requested
    return DEFAULT_SUPPORT_LEVEL_BY_STACK.get(detected_stack, "l0")


def _downgrade_support_level(level: AppliedSupportLevel) -> AppliedSupportLevel:
    return _SUPPORT_LEVEL_DOWNGRADE[level]


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


def _resolve_changed_files(repo_path: Path, base: str | None, *, sinks: PipelineSinks | None = None) -> set[str] | None:
    active_sinks = sinks or PipelineSinks()
    return active_sinks.changed_files.resolve(repo_path, base)


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


def _filter_signals_to_impacted(signals: SignalBundle, changed_files: set[str]) -> SignalBundle:
    changed = {_normalize_path(path) for path in changed_files}
    filtered = []
    for signal in signals.signals:
        source_file = _source_file_ref(signal.source_ref)
        if source_file in changed:
            filtered.append(signal)
            continue
        if any(_source_file_ref(ref) in changed for ref in signal.evidence_refs):
            filtered.append(signal)
    return SignalBundle(signals=filtered, supported_kinds=set(signals.supported_kinds))


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


@dataclass
class _PreflightStage:
    preflight: PreflightResult
    plugin: CollectorPlugin | None
    support_level_applied: AppliedSupportLevel
    competitive_mode: CompetitiveMode


@dataclass
class _CollectStage:
    artifacts: ArtifactBundle
    signals: SignalBundle


@dataclass
class _ScopeStage:
    analysis_scope: AnalysisScope
    analysis_graph: Graph
    analysis_signals: SignalBundle
    fallback_reason: str | None


@dataclass
class _AnalysisStage:
    deterministic_graph: Graph
    analysis_graph: Graph
    findings_raw: FindingsReport
    findings: FindingsReport
    summary: RunSummary
    test_plan: TestPlan
    suppressed_count: int
    verified_fingerprints: set[str]
    policy: PolicyConfig


def _stage_preflight(
    ctx: RunContext,
    *,
    sinks: PipelineSinks,
    total_steps: int,
    notes: list[str],
) -> tuple[_PreflightStage | None, int | None]:
    t = sinks.progress.start(1, total_steps, "Stack detection and pre-flight")
    detection = detect_stack(ctx.repo_path)
    notes.append(f"Detected stack: {detection.stack_id} (confidence: {detection.confidence}).")
    support_level_applied = _resolve_support_level(ctx.support_level, detection.stack_id)
    competitive_mode = _resolve_competitive_mode(ctx.analysis_engine)
    if ctx.risk_policy != "balanced":
        notes.append(f"Risk policy: {ctx.risk_policy}.")

    plugin = get_plugin_for_stack(detection.stack_id)
    if plugin is None and support_level_applied != "l0":
        sinks.progress.finish(1, total_steps, "Stack detection and pre-flight", t)
        notes.append(f"Support level applied: {support_level_applied}.")
        notes.extend(detection.reasons)
        notes.append(f"No collector plugin is registered for stack '{detection.stack_id}'.")
        return None, 2

    if plugin is None:
        preflight = PreflightResult(
            status="WARN",
            reasons=[*detection.reasons, "Unknown stack: fallback to L0 generic advisory mode."],
        )
    else:
        preflight = plugin.preflight(ctx.repo_path, probe_data=detection.probe_data)
    sinks.progress.finish(1, total_steps, "Stack detection and pre-flight", t)

    if preflight.status == "FAIL":
        notes.append(f"Support level applied: {support_level_applied}.")
        notes.extend(preflight.reasons)
        return None, 2
    if preflight.status == "WARN":
        notes.extend(preflight.reasons)
        if plugin is not None and ctx.support_level == "auto":
            downgraded = _downgrade_support_level(support_level_applied)
            if downgraded != support_level_applied:
                notes.append(
                    f"Support level downgraded from {support_level_applied} to {downgraded} due to pre-flight warnings."
                )
                support_level_applied = downgraded

    notes.append(f"Support level applied: {support_level_applied}.")

    return (
        _PreflightStage(
            preflight=preflight,
            plugin=plugin,
            support_level_applied=support_level_applied,
            competitive_mode=competitive_mode,
        ),
        None,
    )


def _stage_collect_artifacts(
    ctx: RunContext,
    *,
    plugin: CollectorPlugin | None,
    sinks: PipelineSinks,
    total_steps: int,
) -> _CollectStage:
    t = sinks.progress.start(2, total_steps, "Collecting artifacts")
    artifacts = ArtifactBundle() if plugin is None else plugin.collect(ctx.repo_path)
    collect_signals_from_artifacts = getattr(plugin, "collect_signals_from_artifacts", None) if plugin is not None else None
    if callable(collect_signals_from_artifacts):
        signals = collect_signals_from_artifacts(artifacts)
    else:
        signals = artifact_bundle_to_signal_bundle(artifacts)
    sinks.progress.finish(2, total_steps, "Collecting artifacts", t)
    return _CollectStage(artifacts=artifacts, signals=signals)


def _stage_build_graph(
    signals: SignalBundle,
    *,
    sinks: PipelineSinks,
    total_steps: int,
) -> Graph:
    t = sinks.progress.start(3, total_steps, "Building graph")
    graph = build_graph(signals)
    sinks.progress.finish(3, total_steps, "Building graph", t)
    return graph


def _stage_resolve_scope(
    ctx: RunContext,
    graph: Graph,
    signals: SignalBundle,
    *,
    sinks: PipelineSinks,
    notes: list[str],
) -> _ScopeStage:
    analysis_scope: AnalysisScope = "full"
    analysis_graph = graph
    analysis_signals = signals
    fallback_reason: str | None = None
    if ctx.mode == "pr":
        if _baseline_graph_is_valid(ctx.baseline_graph):
            changed_files = _resolve_changed_files(ctx.repo_path, ctx.base, sinks=sinks)
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
                    analysis_signals = _filter_signals_to_impacted(signals, changed_files)
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

    return _ScopeStage(
        analysis_scope=analysis_scope,
        analysis_graph=analysis_graph,
        analysis_signals=analysis_signals,
        fallback_reason=fallback_reason,
    )


def _resolve_provider_for_analysis(
    ctx: RunContext,
    *,
    sinks: PipelineSinks,
    notes: list[str],
) -> tuple[ProviderResolution | None, int | None]:
    ci = sinks.environment.is_ci()
    force_no_llm = ctx.no_llm or ctx.analysis_engine == "deterministic"
    provider_resolution = resolve_provider(ctx.provider, no_llm=force_no_llm, ci=ci)
    notes.extend(provider_resolution.notes)
    if not force_no_llm and ctx.provider in {"api", "cli"} and provider_resolution.provider == "none":
        return None, 1
    return provider_resolution, None


def _stage_analysis(
    ctx: RunContext,
    *,
    scope: _ScopeStage,
    support_level_applied: AppliedSupportLevel,
    competitive_mode: CompetitiveMode,
    sinks: PipelineSinks,
    total_steps: int,
    notes: list[str],
) -> tuple[_AnalysisStage | None, int | None]:
    t = sinks.progress.start(4, total_steps, "Running deterministic rules")
    findings_raw = run_rules(scope.analysis_graph, risk_policy=ctx.risk_policy)
    sinks.progress.finish(4, total_steps, "Running deterministic rules", t)
    deterministic_graph = scope.analysis_graph

    suppress_path = ctx.suppress_file
    if suppress_path is None:
        default = ctx.repo_path / ".airiskignore"
        suppress_path = default if default.is_file() else None
    suppressions, suppression_notes = load_suppressions(suppress_path)
    notes.extend(suppression_notes)
    findings_raw, suppressed_count = apply_suppressions(findings_raw, suppressions)
    if suppressed_count:
        notes.append(f"Suppressed findings: {suppressed_count}.")

    provider_resolution, provider_exit = _resolve_provider_for_analysis(ctx, sinks=sinks, notes=notes)
    if provider_exit is not None or provider_resolution is None:
        return None, provider_exit

    t = sinks.progress.start(5, total_steps, "Semantic AI risk stage")
    semantic_signals, semantic_signal_notes = generate_semantic_signals(
        scope.analysis_graph,
        provider=provider_resolution.provider,
        generated_without_llm=provider_resolution.generated_without_llm,
    )
    notes.extend(semantic_signal_notes)
    filtered_semantic_signals = merge_signal_bundles(semantic_signals, min_confidence=ctx.min_confidence)
    semantic_signal_count = len(filtered_semantic_signals.signals)
    merged_signals = merge_signal_bundles(scope.analysis_signals, filtered_semantic_signals, min_confidence="low")
    semantic_graph = build_graph(merged_signals)
    semantic_findings = FindingsReport(findings=[], generated_without_llm=True)
    if ctx.analysis_engine != "deterministic":
        semantic_findings, semantic_notes = generate_semantic_findings(
            semantic_graph,
            provider=provider_resolution.provider,
            generated_without_llm=provider_resolution.generated_without_llm,
        )
        notes.extend(semantic_notes)
    else:
        notes.append("analysis_engine=deterministic: semantic AI stage skipped.")
    sinks.progress.finish(5, total_steps, "Semantic AI risk stage", t)

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

    policy_path = ctx.repo_path / ".airiskpolicy"
    policy, policy_notes = load_policy(policy_path if policy_path.is_file() else None)
    notes.extend(policy_notes)
    merged_findings, policy_dropped, policy_severity_overrides = apply_policy(merged_findings, policy)
    if policy_dropped:
        notes.append(f"Policy filtered findings: {policy_dropped}.")
    if policy_severity_overrides:
        notes.append(f"Policy severity overrides applied: {policy_severity_overrides}.")

    fallback_reason = scope.fallback_reason
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
    graph_mode_applied: GraphMode = "enriched" if semantic_signal_count > 0 else "deterministic"
    summary.graph_mode_applied = graph_mode_applied
    summary.semantic_signal_count = semantic_signal_count
    effective_ci_mode, ci_mode_note = _resolve_effective_ci_mode(ctx.ci_mode, support_level_applied)
    summary.effective_ci_mode = effective_ci_mode
    if ci_mode_note:
        notes.append(ci_mode_note)

    t = sinks.progress.start(6, total_steps, "QA strategy agent")
    test_plan = generate_test_plan(
        findings,
        semantic_graph,
        provider=provider_resolution.provider,
        generated_without_llm=provider_resolution.generated_without_llm or ctx.analysis_engine == "deterministic",
    )
    sinks.progress.finish(6, total_steps, "QA strategy agent", t)

    return (
        _AnalysisStage(
            deterministic_graph=deterministic_graph,
            analysis_graph=semantic_graph,
            findings_raw=findings_raw,
            findings=findings,
            summary=summary,
            test_plan=test_plan,
            suppressed_count=suppressed_count,
            verified_fingerprints=verified_fingerprints,
            policy=policy,
        ),
        None,
    )


def _resolve_exit_code(
    ctx: RunContext,
    result: PipelineResult,
    *,
    policy: PolicyConfig,
    effective_ci_mode: CIMode,
    verified_fingerprints: set[str],
    notes: list[str],
) -> int:
    blocking_findings = [finding for finding in result.findings.findings if is_blocking_enabled_for_finding(policy, finding)]
    exit_code = 0
    if ctx.fail_on_severity:
        max_sev = _max_severity([finding.severity for finding in blocking_findings])
        if max_sev and SEVERITY_RANK.get(max_sev, 0) >= SEVERITY_RANK[ctx.fail_on_severity]:
            notes.append(f"Fail-on-severity triggered: found '{max_sev}' which is >= threshold '{ctx.fail_on_severity}'.")
            exit_code = 3

    if effective_ci_mode == "soft":
        if any(
            finding.status == "new" and SEVERITY_RANK.get(finding.severity, 0) >= SEVERITY_RANK["high"]
            for finding in blocking_findings
        ):
            notes.append("ci_mode=soft triggered: new high/critical finding exists.")
            exit_code = 3
    elif effective_ci_mode == "block_new_critical":
        if any(
            finding.status == "new"
            and finding.severity == "critical"
            and finding.confidence == "high"
            and finding.fingerprint in verified_fingerprints
            for finding in blocking_findings
        ):
            notes.append("ci_mode=block_new_critical triggered: verified high-confidence new critical finding exists.")
            exit_code = 3

    return exit_code


def run_pipeline(ctx: RunContext, *, sinks: PipelineSinks | None = None) -> tuple[PipelineResult | None, int, list[str]]:
    active_sinks = sinks or PipelineSinks()
    pipeline_started = time.perf_counter()
    total_steps = 6
    notes: list[str] = []

    preflight_stage, preflight_exit = _stage_preflight(ctx, sinks=active_sinks, total_steps=total_steps, notes=notes)
    if preflight_exit is not None or preflight_stage is None:
        return None, preflight_exit or 2, notes

    collected_stage = _stage_collect_artifacts(
        ctx,
        plugin=preflight_stage.plugin,
        sinks=active_sinks,
        total_steps=total_steps,
    )
    graph = _stage_build_graph(collected_stage.signals, sinks=active_sinks, total_steps=total_steps)
    scope_stage = _stage_resolve_scope(ctx, graph, collected_stage.signals, sinks=active_sinks, notes=notes)
    analysis_stage, analysis_exit = _stage_analysis(
        ctx,
        scope=scope_stage,
        support_level_applied=preflight_stage.support_level_applied,
        competitive_mode=preflight_stage.competitive_mode,
        sinks=active_sinks,
        total_steps=total_steps,
        notes=notes,
    )
    if analysis_exit is not None or analysis_stage is None:
        return None, analysis_exit or 1, notes

    duration_ms = int((time.perf_counter() - pipeline_started) * 1000)
    run_metrics = _compute_run_metrics(
        analysis_stage.findings,
        analysis_stage.summary,
        support_level_applied=analysis_stage.summary.support_level_applied,
        competitive_mode=analysis_stage.summary.competitive_mode,
        verification_pass_rate=analysis_stage.summary.verification_pass_rate,
        evidence_completeness=analysis_stage.summary.evidence_completeness,
        analysis_scope=scope_stage.analysis_scope,
        duration_ms=duration_ms,
    )

    result = PipelineResult(
        preflight=preflight_stage.preflight,
        analysis_scope=scope_stage.analysis_scope,
        data_quality_low_confidence_ratio=low_confidence_ratio(analysis_stage.analysis_graph),
        suppressed_count=analysis_stage.suppressed_count,
        graph=analysis_stage.analysis_graph,
        deterministic_graph=analysis_stage.deterministic_graph,
        findings_raw=analysis_stage.findings_raw,
        findings=analysis_stage.findings,
        test_plan=analysis_stage.test_plan,
        summary=analysis_stage.summary,
        run_metrics=run_metrics,
    )

    exit_code = _resolve_exit_code(
        ctx,
        result,
        policy=analysis_stage.policy,
        effective_ci_mode=analysis_stage.summary.effective_ci_mode,
        verified_fingerprints=analysis_stage.verified_fingerprints,
        notes=notes,
    )

    output_notes = active_sinks.artifacts.write(ctx=ctx, result=result, notes=notes)
    notes.extend(output_notes)

    return result, exit_code, notes
