from __future__ import annotations

import json
from typing import cast

from ai_risk_manager.agents.llm_runtime import LLMRuntimeError, call_llm_json
from ai_risk_manager.schemas.types import Confidence, Graph
from ai_risk_manager.signals.types import CapabilitySignal, SignalBundle, SignalKind

_MAX_CONTEXT_ITEMS = 120
_ALLOWED_CONFIDENCE: set[str] = {"high", "medium", "low"}
_ALLOWED_SIGNAL_KINDS: set[str] = {
    "http_write_surface",
    "request_contract_binding",
    "state_transition_declared",
    "state_transition_handled_guarded",
    "test_to_endpoint_coverage",
    "dependency_version_policy",
    "side_effect_emit_contract",
    "authorization_boundary_enforced",
}
_REQUIRED_ATTRS_BY_KIND: dict[str, set[str]] = {
    "http_write_surface": {"endpoint_name", "method", "path"},
    "request_contract_binding": {"endpoint_name", "model_name"},
    "state_transition_declared": {"machine", "source_state", "target_state"},
    "state_transition_handled_guarded": {"machine", "source_state", "target_state", "invariant_guarded"},
    "test_to_endpoint_coverage": {"test_name"},
    "dependency_version_policy": {"dependency_name", "scope"},
    "side_effect_emit_contract": {"trigger", "side_effect"},
    "authorization_boundary_enforced": {"boundary", "enforcement"},
}


def _has_non_empty_attr(attributes: dict, key: str) -> bool:
    value = attributes.get(key)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _graph_context(graph: Graph) -> dict:
    items: list[dict] = []
    for node in graph.nodes:
        snippet = node.details.get("snippet")
        if not snippet:
            continue
        items.append(
            {
                "node_id": node.id,
                "node_type": node.type,
                "source_ref": node.source_ref,
                "snippet": snippet,
                "method": node.details.get("method"),
                "path": node.details.get("path"),
            }
        )
        if len(items) >= _MAX_CONTEXT_ITEMS:
            break
    return {"items": items, "node_count": len(graph.nodes), "edge_count": len(graph.edges)}


def _validate_semantic_signal_payload(payload: dict) -> SignalBundle:
    rows = payload.get("signals")
    if not isinstance(rows, list):
        raise ValueError("Semantic signal payload must contain list field 'signals'")

    signals: list[CapabilitySignal] = []
    supported_kinds: set[SignalKind] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each semantic signal row must be an object")

        kind = str(row.get("kind", "")).strip()
        if kind not in _ALLOWED_SIGNAL_KINDS:
            raise ValueError(f"Unsupported semantic signal kind: {kind!r}")

        confidence = str(row.get("confidence", "")).strip().lower()
        if confidence not in _ALLOWED_CONFIDENCE:
            raise ValueError(f"Unsupported semantic signal confidence: {confidence!r}")

        source_ref = str(row.get("source_ref", "")).strip()
        if not source_ref:
            raise ValueError("Each semantic signal must include non-empty source_ref")

        evidence_refs = row.get("evidence_refs")
        if not isinstance(evidence_refs, list) or not evidence_refs or not all(isinstance(ref, str) for ref in evidence_refs):
            raise ValueError("Each semantic signal must include non-empty list field 'evidence_refs' with string refs")

        attributes = row.get("attributes", {})
        if not isinstance(attributes, dict):
            raise ValueError("Semantic signal attributes must be an object")
        required_attrs = _REQUIRED_ATTRS_BY_KIND[kind]
        missing = [key for key in required_attrs if not _has_non_empty_attr(attributes, key)]
        if missing:
            raise ValueError(f"Semantic signal '{kind}' is missing required attributes: {missing}")
        if kind == "test_to_endpoint_coverage":
            has_http_shape = _has_non_empty_attr(attributes, "method") and _has_non_empty_attr(attributes, "path")
            has_fallback_shape = str(attributes.get("coverage_mode", "")).strip() == "name_fallback_candidate"
            if not (has_http_shape or has_fallback_shape):
                raise ValueError(
                    "Semantic signal 'test_to_endpoint_coverage' must include method/path or coverage_mode=name_fallback_candidate"
                )

        tags = row.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise ValueError("Semantic signal tags must be a list of strings")

        cast_kind = cast(SignalKind, kind)
        supported_kinds.add(cast_kind)
        signals.append(
            CapabilitySignal(
                id=str(row.get("id") or f"semantic:{kind}:{source_ref}"),
                kind=cast_kind,
                source_ref=source_ref,
                confidence=cast(Confidence, confidence),
                evidence_refs=evidence_refs,
                attributes=attributes,
                tags=tags,
                origin="ai",
            )
        )

    return SignalBundle(signals=signals, supported_kinds=supported_kinds)


def generate_semantic_signals(
    graph: Graph,
    *,
    provider: str,
    generated_without_llm: bool,
) -> tuple[SignalBundle, list[str]]:
    if generated_without_llm or provider == "none":
        return SignalBundle(), ["Semantic signal stage skipped (no LLM backend)."]

    prompt_payload = {
        "task": "Return capability signals as JSON using grounded repository context only.",
        "rules": [
            "Return only JSON object with key 'signals'.",
            (
                "Each signal must include: id, kind, source_ref, confidence, evidence_refs, "
                "attributes, tags."
            ),
            "Do not produce signals without concrete evidence_refs.",
            "Use only allowed signal kinds.",
        ],
        "allowed_signal_kinds": sorted(_ALLOWED_SIGNAL_KINDS),
        "graph_context": _graph_context(graph),
    }
    prompt = json.dumps(prompt_payload, ensure_ascii=False)

    try:
        payload = call_llm_json(provider, prompt, max_retries=2)
        bundle = _validate_semantic_signal_payload(payload)
        if not bundle.signals:
            return bundle, ["Semantic signal stage returned zero signals."]
        return bundle, [f"Semantic signal stage produced {len(bundle.signals)} signal(s)."]
    except (LLMRuntimeError, ValueError, KeyError, TypeError) as exc:
        return SignalBundle(), [f"Semantic signal stage degraded: {exc}"]
