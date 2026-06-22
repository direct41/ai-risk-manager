from __future__ import annotations

from ai_risk_manager.schemas.types import Graph, Node

_ARCHITECTURE_NODE_TYPES = {"API", "Entity", "Transition", "DataStore", "ExternalSystem", "TestCase"}
_ARCHITECTURE_EDGE_TYPES = {"covered_by", "triggers", "validated_by", "writes"}


def _label(value: object) -> str:
    return str(value).replace("\n", " ").replace('"', "'").replace("[", "(").replace("]", ")")


def _node_label(node: Node) -> str:
    if node.type == "API":
        method = str(node.details.get("method", "")).strip().upper()
        path = str(node.details.get("path", "")).strip()
        if method and path:
            return f"API: {method} {path}"
    if node.type == "TestCase":
        test_type = str(node.details.get("test_type", "unit"))
        return f"TestCase ({test_type}): {node.name}"
    return f"{node.type}: {node.name}"


def render_entity_relationship_mermaid(graph: Graph) -> str:
    nodes = sorted((node for node in graph.nodes if node.type in _ARCHITECTURE_NODE_TYPES), key=lambda row: row.id)
    node_ids = {node.id: f"n{index}" for index, node in enumerate(nodes)}
    lines = ["flowchart LR"]
    if not nodes:
        lines.append('  empty["No architecture relationships detected"]')
        return "\n".join(lines) + "\n"

    for node in nodes:
        lines.append(f'  {node_ids[node.id]}["{_label(_node_label(node))}"]')
    for edge in sorted(graph.edges, key=lambda row: row.id):
        source_id = node_ids.get(edge.source_node_id)
        target_id = node_ids.get(edge.target_node_id)
        if source_id is None or target_id is None or edge.type not in _ARCHITECTURE_EDGE_TYPES:
            continue
        lines.append(f'  {source_id} -->|"{_label(edge.type)}"| {target_id}')
    return "\n".join(lines) + "\n"


def render_state_transitions_mermaid(graph: Graph) -> str:
    transitions = [
        *(('declared', row) for row in graph.declared_transitions),
        *(('handled', row) for row in graph.handled_transitions),
    ]
    lines = ["stateDiagram-v2"]
    if not transitions:
        lines.append("  %% No state transitions detected")
        return "\n".join(lines) + "\n"

    states = sorted({row.source for _, row in transitions} | {row.target for _, row in transitions})
    state_ids = {state: f"s{index}" for index, state in enumerate(states)}
    for state in states:
        lines.append(f'  state "{_label(state)}" as {state_ids[state]}')

    seen: set[tuple[str, str, str, str]] = set()
    for status, transition in transitions:
        key = (status, transition.machine, transition.source, transition.target)
        if key in seen:
            continue
        seen.add(key)
        label = _label(f"{status}: {transition.machine}")
        lines.append(f"  {state_ids[transition.source]} --> {state_ids[transition.target]}: {label}")
    return "\n".join(lines) + "\n"


__all__ = ["render_entity_relationship_mermaid", "render_state_transitions_mermaid"]
