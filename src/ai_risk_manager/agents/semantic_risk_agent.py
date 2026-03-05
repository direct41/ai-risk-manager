from __future__ import annotations

import json
import os
from typing import cast

from ai_risk_manager.agents.llm_runtime import LLMRuntimeError, call_llm_json
from ai_risk_manager.schemas.types import Confidence, Finding, FindingsReport, Graph, Severity

_MAX_CONTEXT_ITEMS = 120
_ALLOWED_SEVERITY: set[str] = {"critical", "high", "medium", "low"}
_ALLOWED_CONFIDENCE: set[str] = {"high", "medium", "low"}


def _semantic_llm_timeout_seconds() -> float:
    raw = os.getenv("AIRISK_SEMANTIC_LLM_TIMEOUT_SECONDS", "20")
    try:
        value = float(raw)
    except ValueError:
        return 20.0
    return value if value > 0 else 20.0


def _semantic_llm_max_retries() -> int:
    raw = os.getenv("AIRISK_SEMANTIC_LLM_MAX_RETRIES", "0")
    try:
        value = int(raw)
    except ValueError:
        return 0
    return value if value >= 0 else 0


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


def _validate_semantic_payload(payload: dict) -> FindingsReport:
    rows = payload.get("findings")
    if not isinstance(rows, list):
        raise ValueError("Semantic findings payload must contain list field 'findings'")

    findings: list[Finding] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each semantic finding row must be an object")
        evidence_refs = row.get("evidence_refs")
        if not isinstance(evidence_refs, list) or not all(isinstance(ref, str) for ref in evidence_refs):
            raise ValueError("Each semantic finding must include list field 'evidence_refs' with string refs")
        severity = str(row.get("severity", "")).strip().lower()
        if severity not in _ALLOWED_SEVERITY:
            raise ValueError(f"Unsupported semantic finding severity: {severity!r}")
        confidence = str(row.get("confidence", "")).strip().lower()
        if confidence not in _ALLOWED_CONFIDENCE:
            raise ValueError(f"Unsupported semantic finding confidence: {confidence!r}")

        findings.append(
            Finding(
                id=str(row["id"]),
                rule_id=str(row["rule_id"]),
                title=str(row["title"]),
                description=str(row["description"]),
                severity=cast(Severity, severity),
                confidence=cast(Confidence, confidence),
                evidence=str(row["evidence"]),
                source_ref=str(row["source_ref"]),
                suppression_key=str(row.get("suppression_key") or f"{row['rule_id']}:{row['id']}"),
                recommendation=str(row["recommendation"]),
                origin="ai",
                fingerprint=str(row.get("fingerprint", "")),
                status="unchanged",
                evidence_refs=evidence_refs,
                generated_without_llm=False,
            )
        )
    return FindingsReport(findings=findings, generated_without_llm=False)


def generate_semantic_findings(
    graph: Graph,
    *,
    provider: str,
    generated_without_llm: bool,
) -> tuple[FindingsReport, list[str]]:
    if generated_without_llm or provider == "none":
        return FindingsReport(findings=[], generated_without_llm=True), ["Semantic AI stage skipped (no LLM backend)."]

    prompt_payload = {
        "task": "Return risk findings as JSON using grounded repository context only.",
        "rules": [
            "Return only JSON object with key 'findings'.",
            "Each finding must include: id, rule_id, title, description, severity, confidence, evidence, source_ref, recommendation, evidence_refs.",
            "Do not produce findings without concrete evidence_refs.",
        ],
        "graph_context": _graph_context(graph),
    }
    prompt = json.dumps(prompt_payload, ensure_ascii=False)

    try:
        payload = call_llm_json(
            provider,
            prompt,
            max_retries=_semantic_llm_max_retries(),
            timeout_seconds=_semantic_llm_timeout_seconds(),
        )
        report = _validate_semantic_payload(payload)
        if not report.findings:
            return report, ["Semantic AI stage returned zero findings."]
        return report, [f"Semantic AI stage produced {len(report.findings)} finding(s)."]
    except (LLMRuntimeError, ValueError, KeyError, TypeError) as exc:
        return FindingsReport(findings=[], generated_without_llm=True), [f"Semantic AI stage degraded: {exc}"]
