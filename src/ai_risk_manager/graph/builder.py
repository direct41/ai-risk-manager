from __future__ import annotations

import re

from ai_risk_manager.collectors.collector import ArtifactBundle
from ai_risk_manager.schemas.types import Edge, Graph, Node, TransitionSpec


def _safe_id(value: str) -> str:
    return value.replace("/", ":").replace("\\", ":").replace(" ", "_")


def _tokens(value: str) -> set[str]:
    return {tok for tok in re.split(r"[^a-zA-Z0-9]+", value.lower()) if tok}


def build_graph(artifacts: ArtifactBundle) -> Graph:
    graph = Graph()

    for file_path, model_name in artifacts.pydantic_models:
        model_node_id = f"entity:{_safe_id(file_path)}:{model_name}"
        graph.nodes.append(
            Node(
                id=model_node_id,
                type="Entity",
                name=model_name,
                layer="domain",
                source_ref=file_path,
                confidence="high",
            )
        )

    for file_path, endpoint_name in artifacts.write_endpoints:
        api_node_id = f"api:{_safe_id(file_path)}:{endpoint_name}"
        graph.nodes.append(
            Node(
                id=api_node_id,
                type="API",
                name=endpoint_name,
                layer="infrastructure",
                source_ref=file_path,
                confidence="high",
            )
        )

    for test_file_path, test_name in artifacts.test_cases:
        test_node_id = f"test:{_safe_id(test_file_path)}:{test_name}"
        graph.nodes.append(
            Node(
                id=test_node_id,
                type="TestCase",
                name=test_name,
                layer="qa",
                source_ref=test_file_path,
                confidence="high",
            )
        )

    model_node_ids = {n.name: n.id for n in graph.nodes if n.type == "Entity"}
    api_node_ids = {n.name: n.id for n in graph.nodes if n.type == "API"}
    for file_path, endpoint_name, model_name in artifacts.endpoint_models:
        api_id = api_node_ids.get(endpoint_name)
        model_id = model_node_ids.get(model_name)
        if not api_id or not model_id:
            continue
        graph.edges.append(
            Edge(
                id=f"edge:{api_id}->{model_id}:validated_by",
                source_node_id=api_id,
                target_node_id=model_id,
                type="validated_by",
                source_ref=file_path,
                evidence=f"endpoint '{endpoint_name}' uses pydantic model '{model_name}'",
                confidence="high",
            )
        )

    # Coarse heuristic: connect tests to endpoints when names overlap.
    api_nodes = [n for n in graph.nodes if n.type == "API"]
    test_nodes = [n for n in graph.nodes if n.type == "TestCase"]
    for api in api_nodes:
        api_tokens = _tokens(api.name)
        for test in test_nodes:
            test_tokens = _tokens(test.name)
            if api_tokens and api_tokens.issubset(test_tokens):
                graph.edges.append(
                    Edge(
                        id=f"edge:{test.id}->{api.id}",
                        source_node_id=test.id,
                        target_node_id=api.id,
                        type="covered_by",
                        source_ref=test.source_ref,
                        evidence=f"name overlap: {test.name} ~ {api.name}",
                        confidence="medium",
                    )
                )

    seen_states: set[str] = set()
    for file_path, machine, src, dst in artifacts.declared_transitions:
        for state in (src, dst):
            state_id = f"state:{machine}:{state}"
            if state_id in seen_states:
                continue
            seen_states.add(state_id)
            graph.nodes.append(
                Node(
                    id=state_id,
                    type="State",
                    name=state,
                    layer="domain",
                    source_ref=file_path,
                    confidence="high",
                )
            )

    for file_path, machine, src, dst in artifacts.declared_transitions:
        graph.declared_transitions.append(TransitionSpec(machine=machine, source=src, target=dst, source_ref=file_path))
        transition_node_id = f"transition:{machine}:{src}->{dst}:declared"
        graph.nodes.append(
            Node(
                id=transition_node_id,
                type="Transition",
                name=f"{src}->{dst}",
                layer="domain",
                source_ref=file_path,
                confidence="high",
            )
        )
        graph.edges.append(
            Edge(
                id=f"edge:state:{machine}:{src}->state:{machine}:{dst}:declared",
                source_node_id=f"state:{machine}:{src}",
                target_node_id=f"state:{machine}:{dst}",
                type="transitions_to",
                source_ref=file_path,
                evidence=f"declared transition in {machine}",
                confidence="high",
            )
        )

    for file_path, machine, src, dst in artifacts.handled_transitions:
        graph.handled_transitions.append(TransitionSpec(machine=machine, source=src, target=dst, source_ref=file_path))

    return graph


def low_confidence_ratio(graph: Graph) -> float:
    total = len(graph.nodes) + len(graph.edges)
    if total == 0:
        return 0.0

    low = sum(1 for n in graph.nodes if n.confidence == "low")
    low += sum(1 for e in graph.edges if e.confidence == "low")
    return low / total
