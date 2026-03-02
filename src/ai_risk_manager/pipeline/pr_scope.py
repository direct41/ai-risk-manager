from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ai_risk_manager.pipeline.sinks import PipelineSinks
from ai_risk_manager.schemas.types import Graph
from ai_risk_manager.signals.types import SignalBundle


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def _source_file_ref(source_ref: str) -> str:
    normalized = _normalize_path(source_ref)
    parts = normalized.rsplit(":", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return normalized


def baseline_graph_is_valid(path: Path | None) -> bool:
    if not path or not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and isinstance(payload.get("nodes"), list)


def load_baseline_fingerprints(baseline_graph: Path | None) -> tuple[set[str] | None, str | None]:
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


def resolve_changed_files(repo_path: Path, base: str | None, *, sinks: PipelineSinks | None = None) -> set[str] | None:
    active_sinks = sinks or PipelineSinks()
    return active_sinks.changed_files.resolve(repo_path, base)


def filter_graph_to_impacted(graph: Graph, changed_files: set[str]) -> Graph:
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
    declared = [
        transition for transition in graph.declared_transitions if _source_file_ref(transition.source_ref) in changed
    ]
    handled = [
        transition for transition in graph.handled_transitions if _source_file_ref(transition.source_ref) in changed
    ]
    return Graph(nodes=nodes, edges=edges, declared_transitions=declared, handled_transitions=handled)


def filter_signals_to_impacted(signals: SignalBundle, changed_files: set[str]) -> SignalBundle:
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
