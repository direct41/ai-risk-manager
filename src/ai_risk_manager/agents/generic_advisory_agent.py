from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast

from ai_risk_manager.agents.llm_runtime import LLMRuntimeError, call_llm_json
from ai_risk_manager.schemas.types import Confidence, Finding, FindingsReport, Severity

_MAX_CONTEXT_FILES = 24
_MAX_FILE_LINES = 80
_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".riskmap",
    "dist",
    "build",
    "coverage",
    "eval",
}
_ALLOWED_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".java",
    ".rb",
    ".php",
    ".rs",
    ".sh",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
    ".md",
}
_ALLOWED_FILENAMES = {
    "Dockerfile",
    "Makefile",
    "requirements.txt",
    "pyproject.toml",
    "package.json",
}
_ALLOWED_SEVERITY: set[str] = {"critical", "high", "medium", "low"}
_ALLOWED_CONFIDENCE: set[str] = {"high", "medium", "low"}


def _generic_llm_timeout_seconds() -> float:
    raw = os.getenv("AIRISK_GENERIC_LLM_TIMEOUT_SECONDS", "25")
    try:
        value = float(raw)
    except ValueError:
        return 25.0
    return value if value > 0 else 25.0


def _generic_llm_max_retries() -> int:
    raw = os.getenv("AIRISK_GENERIC_LLM_MAX_RETRIES", "0")
    try:
        value = int(raw)
    except ValueError:
        return 0
    return value if value >= 0 else 0


def _iter_context_files(repo_path: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(repo_path.rglob("*")):
        if any(part in _EXCLUDED_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() not in _ALLOWED_SUFFIXES and path.name not in _ALLOWED_FILENAMES:
            continue
        files.append(path)
        if len(files) >= _MAX_CONTEXT_FILES:
            break
    return files


def _read_snippet(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return ""
    snippet_lines = lines[:_MAX_FILE_LINES]
    return "\n".join(f"{idx}: {line}" for idx, line in enumerate(snippet_lines, start=1)).strip()


def _repo_context(repo_path: Path) -> dict[str, object]:
    items: list[dict[str, str]] = []
    for path in _iter_context_files(repo_path):
        snippet = _read_snippet(path)
        if not snippet:
            continue
        items.append(
            {
                "path": str(path.relative_to(repo_path)),
                "snippet": snippet,
            }
        )
    return {"files": items, "file_count": len(items)}


def _validate_advisory_payload(payload: dict) -> FindingsReport:
    rows = payload.get("findings")
    if not isinstance(rows, list):
        raise ValueError("Generic advisory payload must contain list field 'findings'")

    findings: list[Finding] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each advisory finding row must be an object")

        evidence_refs = row.get("evidence_refs")
        if not isinstance(evidence_refs, list) or not evidence_refs or not all(isinstance(ref, str) for ref in evidence_refs):
            raise ValueError("Each advisory finding must include non-empty list field 'evidence_refs'")

        severity = str(row.get("severity", "")).strip().lower()
        if severity not in _ALLOWED_SEVERITY:
            raise ValueError(f"Unsupported advisory finding severity: {severity!r}")

        confidence = str(row.get("confidence", "")).strip().lower()
        if confidence not in _ALLOWED_CONFIDENCE:
            raise ValueError(f"Unsupported advisory finding confidence: {confidence!r}")

        source_ref = str(row.get("source_ref", "")).strip()
        if not source_ref:
            raise ValueError("Each advisory finding must include non-empty source_ref")

        rule_id = str(row.get("rule_id", "")).strip()
        if not rule_id:
            raise ValueError("Each advisory finding must include non-empty rule_id")

        findings.append(
            Finding(
                id=str(row.get("id") or f"advisory:{rule_id}:{source_ref}"),
                rule_id=rule_id,
                title=str(row.get("title", "")).strip(),
                description=str(row.get("description", "")).strip(),
                severity=cast(Severity, severity),
                confidence=cast(Confidence, confidence),
                evidence=str(row.get("evidence", "")).strip(),
                source_ref=source_ref,
                suppression_key=str(row.get("suppression_key") or f"{rule_id}:{source_ref}"),
                recommendation=str(row.get("recommendation", "")).strip(),
                origin="ai",
                fingerprint=str(row.get("fingerprint", "")),
                status="unchanged",
                evidence_refs=evidence_refs,
                generated_without_llm=False,
            )
        )
    return FindingsReport(findings=findings, generated_without_llm=False)


def generate_generic_advisory_findings(
    repo_path: Path,
    *,
    provider: str,
    generated_without_llm: bool,
) -> tuple[FindingsReport, list[str]]:
    if generated_without_llm or provider == "none":
        return FindingsReport(findings=[], generated_without_llm=True), ["Generic advisory AI stage skipped (no LLM backend)."]

    context = _repo_context(repo_path)
    if not context["files"]:
        return FindingsReport(findings=[], generated_without_llm=True), ["Generic advisory AI stage skipped (no readable repo context)."]

    prompt_payload = {
        "task": "Return advisory-only repository risk findings as JSON using grounded file snippets only.",
        "rules": [
            "Return only JSON object with key 'findings'.",
            (
                "Each finding must include: id, rule_id, title, description, severity, confidence, evidence, "
                "source_ref, recommendation, evidence_refs."
            ),
            "Only use evidence that is explicitly present in the provided file snippets.",
            "If confidence is low or evidence is weak, return zero findings instead of guessing.",
            "These findings are advisory-only for partially supported repositories.",
        ],
        "repo_context": context,
    }
    prompt = json.dumps(prompt_payload, ensure_ascii=False)

    try:
        payload = call_llm_json(
            provider,
            prompt,
            max_retries=_generic_llm_max_retries(),
            timeout_seconds=_generic_llm_timeout_seconds(),
        )
        report = _validate_advisory_payload(payload)
        if not report.findings:
            return report, ["Generic advisory AI stage returned zero findings."]
        return report, [f"Generic advisory AI stage produced {len(report.findings)} finding(s)."]
    except (LLMRuntimeError, ValueError, KeyError, TypeError) as exc:
        return FindingsReport(findings=[], generated_without_llm=True), [f"Generic advisory AI stage degraded: {exc}"]
