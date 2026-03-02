from __future__ import annotations

import re

from ai_risk_manager.collectors.plugins.base import ArtifactBundle
from ai_risk_manager.schemas.types import Edge, Graph, Node, TransitionSpec


def _safe_id(value: str) -> str:
    return value.replace("/", ":").replace("\\", ":").replace(" ", "_")


def _tokens(value: str) -> set[str]:
    return {tok for tok in re.split(r"[^a-zA-Z0-9]+", value.lower()) if tok}


def _with_line_ref(file_path: str, line: int | None) -> str:
    if line is None:
        return file_path
    return f"{file_path}:{line}"


def _normalize_route_path(path: str) -> str:
    raw = path.strip()
    raw = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^/]+", "", raw)
    raw = raw.split("?", 1)[0].split("#", 1)[0].strip()
    if not raw:
        return "/"
    if not raw.startswith("/"):
        raw = f"/{raw}"
    raw = re.sub(r"/{2,}", "/", raw)
    if len(raw) > 1:
        raw = raw.rstrip("/")
    return raw


def _is_path_param(segment: str) -> bool:
    token = segment.strip()
    if not token:
        return False
    return token.startswith("{") and token.endswith("}")


def _route_paths_match(api_path: str, observed_path: str) -> bool:
    normalized_api = _normalize_route_path(api_path)
    normalized_observed = _normalize_route_path(observed_path)
    if normalized_api == normalized_observed:
        return True

    api_parts = [part for part in normalized_api.split("/") if part]
    observed_parts = [part for part in normalized_observed.split("/") if part]
    if len(api_parts) != len(observed_parts):
        return False

    for api_part, observed_part in zip(api_parts, observed_parts):
        if api_part == observed_part:
            continue
        if _is_path_param(api_part) or _is_path_param(observed_part):
            continue
        return False
    return True


def build_graph(artifacts: ArtifactBundle) -> Graph:
    graph = Graph()

    for file_path, dep_name, raw_spec, line, policy_violation, scope in artifacts.dependency_specs:
        dep_node_id = f"dependency:{_safe_id(file_path)}:{_safe_id(dep_name)}:{line or 0}"
        graph.nodes.append(
            Node(
                id=dep_node_id,
                type="Dependency",
                name=dep_name,
                layer="infrastructure",
                source_ref=_with_line_ref(file_path, line),
                confidence="high",
                details={
                    "spec": raw_spec,
                    "policy_violation": policy_violation,
                    "scope": scope,
                },
            )
        )

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

    api_node_ids_by_name: dict[str, str] = {}
    api_node_ids_by_file_name: dict[tuple[str, str], str] = {}
    api_ids_by_route: dict[tuple[str, str], list[str]] = {}
    api_routes_by_method: dict[str, list[tuple[str, str]]] = {}
    for file_path, endpoint_name, method, route_path, line, snippet in artifacts.write_endpoints:
        api_node_id = f"api:{_safe_id(file_path)}:{endpoint_name}"
        normalized_route_path = _normalize_route_path(route_path)
        api_node_ids_by_name[endpoint_name] = api_node_id
        api_node_ids_by_file_name[(file_path, endpoint_name)] = api_node_id
        api_ids_by_route.setdefault((method.upper(), normalized_route_path), []).append(api_node_id)
        api_routes_by_method.setdefault(method.upper(), []).append((normalized_route_path, api_node_id))
        graph.nodes.append(
            Node(
                id=api_node_id,
                type="API",
                name=endpoint_name,
                layer="infrastructure",
                source_ref=_with_line_ref(file_path, line),
                confidence="high",
                details={
                    "method": method.upper(),
                    "path": normalized_route_path,
                    "snippet": snippet,
                },
            )
        )

    test_node_ids: dict[tuple[str, str], str] = {}
    for test_file_path, test_name, line, snippet in artifacts.test_cases:
        test_node_id = f"test:{_safe_id(test_file_path)}:{test_name}"
        test_node_ids[(test_file_path, test_name)] = test_node_id
        graph.nodes.append(
            Node(
                id=test_node_id,
                type="TestCase",
                name=test_name,
                layer="qa",
                source_ref=_with_line_ref(test_file_path, line),
                confidence="high",
                details={"snippet": snippet},
            )
        )

    model_node_ids = {n.name: n.id for n in graph.nodes if n.type == "Entity"}
    for file_path, endpoint_name, model_name in artifacts.endpoint_models:
        api_id = api_node_ids_by_file_name.get((file_path, endpoint_name)) or api_node_ids_by_name.get(endpoint_name)
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

    covered_pairs: set[tuple[str, str]] = set()
    for test_file_path, test_name, method, route_path, line, snippet in artifacts.test_http_calls:
        test_id = test_node_ids.get((test_file_path, test_name))
        if not test_id:
            continue
        normalized_route_path = _normalize_route_path(route_path)
        matched_api_ids: set[str] = set(api_ids_by_route.get((method.upper(), normalized_route_path), []))
        if not matched_api_ids:
            for api_route, api_id in api_routes_by_method.get(method.upper(), []):
                if _route_paths_match(api_route, normalized_route_path):
                    matched_api_ids.add(api_id)

        for api_id in sorted(matched_api_ids):
            covered_pairs.add((test_id, api_id))
            graph.edges.append(
                Edge(
                    id=f"edge:{test_id}->{api_id}:{method.upper()}:{_safe_id(normalized_route_path)}",
                    source_node_id=test_id,
                    target_node_id=api_id,
                    type="covered_by",
                    source_ref=_with_line_ref(test_file_path, line),
                    evidence=f"test HTTP call: {method.upper()} {normalized_route_path}",
                    confidence="high",
                    details={"snippet": snippet, "method": method.upper(), "path": normalized_route_path},
                )
            )

    # Fallback heuristic: connect tests to endpoints when names overlap.
    api_nodes = [n for n in graph.nodes if n.type == "API"]
    test_nodes = [n for n in graph.nodes if n.type == "TestCase"]
    for api in api_nodes:
        api_tokens = _tokens(api.name)
        for test in test_nodes:
            if (test.id, api.id) in covered_pairs:
                continue
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
                        details={"method": api.details.get("method", ""), "path": api.details.get("path", "")},
                    )
                )

    seen_states: set[str] = set()
    for file_path, machine, src, dst, line, snippet in artifacts.declared_transitions:
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
                    source_ref=_with_line_ref(file_path, line),
                    confidence="high",
                    details={"snippet": snippet},
                )
            )

    for file_path, machine, src, dst, line, snippet in artifacts.declared_transitions:
        graph.declared_transitions.append(
            TransitionSpec(machine=machine, source=src, target=dst, source_ref=_with_line_ref(file_path, line), line=line, snippet=snippet)
        )
        transition_node_id = f"transition:{machine}:{src}->{dst}:declared"
        graph.nodes.append(
            Node(
                id=transition_node_id,
                type="Transition",
                name=f"{src}->{dst}",
                layer="domain",
                source_ref=_with_line_ref(file_path, line),
                confidence="high",
                details={"snippet": snippet},
            )
        )
        graph.edges.append(
            Edge(
                id=f"edge:state:{machine}:{src}->state:{machine}:{dst}:declared",
                source_node_id=f"state:{machine}:{src}",
                target_node_id=f"state:{machine}:{dst}",
                type="transitions_to",
                source_ref=_with_line_ref(file_path, line),
                evidence=f"declared transition in {machine}",
                confidence="high",
                details={"snippet": snippet},
            )
        )

    for file_path, machine, src, dst, line, snippet, invariant_guarded in artifacts.handled_transitions:
        graph.handled_transitions.append(
            TransitionSpec(
                machine=machine,
                source=src,
                target=dst,
                source_ref=_with_line_ref(file_path, line),
                line=line,
                snippet=snippet,
                invariant_guarded=invariant_guarded,
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
