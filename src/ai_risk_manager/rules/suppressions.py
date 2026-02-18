from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from ai_risk_manager.schemas.types import Finding, FindingsReport


@dataclass(frozen=True)
class SuppressionSet:
    keys: set[str]
    rule_file_pairs: set[tuple[str, str]]


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def _unquote(value: str) -> str:
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def load_suppressions(path: Path | None) -> tuple[SuppressionSet, list[str]]:
    if path is None or not path.is_file():
        return SuppressionSet(keys=set(), rule_file_pairs=set()), []

    notes: list[str] = []
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    line_re = re.compile(r"^-?\s*([a-z_]+)\s*:\s*(.+?)\s*$")

    for idx, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        match = line_re.match(line)
        if not match:
            notes.append(f"Ignoring malformed suppression line {idx} in {path.name}.")
            continue

        key, raw_value = match.group(1), match.group(2)
        if line.startswith("-") and current:
            entries.append(current)
            current = {}
        current[key] = _unquote(raw_value)

    if current:
        entries.append(current)

    keys: set[str] = set()
    rule_file_pairs: set[tuple[str, str]] = set()
    for entry in entries:
        suppression_key = entry.get("key")
        if suppression_key:
            keys.add(suppression_key)
            continue

        rule = entry.get("rule")
        file_ref = entry.get("file")
        if rule and file_ref:
            rule_file_pairs.add((rule, _normalize_path(file_ref)))
            continue

        notes.append(f"Ignoring suppression entry without key or rule+file in {path.name}.")

    if keys or rule_file_pairs:
        notes.append(
            f"Loaded suppressions from {path}: {len(keys)} key(s), {len(rule_file_pairs)} rule+file pair(s)."
        )

    return SuppressionSet(keys=keys, rule_file_pairs=rule_file_pairs), notes


def is_suppressed(finding: Finding, suppressions: SuppressionSet) -> bool:
    if finding.suppression_key in suppressions.keys:
        return True
    return (finding.rule_id, _normalize_path(finding.source_ref)) in suppressions.rule_file_pairs


def apply_suppressions(findings: FindingsReport, suppressions: SuppressionSet) -> tuple[FindingsReport, int]:
    kept = [finding for finding in findings.findings if not is_suppressed(finding, suppressions)]
    suppressed_count = len(findings.findings) - len(kept)
    return FindingsReport(findings=kept, generated_without_llm=findings.generated_without_llm), suppressed_count
