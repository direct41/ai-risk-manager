from __future__ import annotations

from ai_risk_manager.collectors.collector import ArtifactBundle
from ai_risk_manager.schemas.types import Edge, Graph, Node


def build_graph(artifacts: ArtifactBundle) -> Graph:
    graph = Graph()

    for file_path, endpoint_name in artifacts.write_endpoints:
        api_node_id = f"api:{endpoint_name}"
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

    for test_file in artifacts.test_files:
        test_name = test_file.stem
        test_node_id = f"test:{test_name}"
        graph.nodes.append(
            Node(
                id=test_node_id,
                type="TestCase",
                name=test_name,
                layer="qa",
                source_ref=str(test_file),
                confidence="high",
            )
        )

    # Coarse heuristic: connect tests to endpoints when names overlap.
    api_nodes = [n for n in graph.nodes if n.type == "API"]
    test_nodes = [n for n in graph.nodes if n.type == "TestCase"]
    for api in api_nodes:
        api_key = api.name.replace("_", "")
        for test in test_nodes:
            if api_key in test.name.replace("_", ""):
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

    return graph


def low_confidence_ratio(graph: Graph) -> float:
    total = len(graph.nodes) + len(graph.edges)
    if total == 0:
        return 0.0

    low = sum(1 for n in graph.nodes if n.confidence == "low")
    low += sum(1 for e in graph.edges if e.confidence == "low")
    return low / total
