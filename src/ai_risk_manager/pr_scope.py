from __future__ import annotations

from typing import Protocol

_PR_SCOPED_RULE_IDS = {"ui_journey_smoke_failed"}
_PR_SCOPED_RULE_PREFIXES = ("pr_",)


class FindingLike(Protocol):
    rule_id: str
    source_ref: str
    evidence_refs: list[str]


def normalize_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def source_ref_path(source_ref: str) -> str:
    parts = source_ref.rsplit(":", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return source_ref


def finding_matches_changed_files(finding: FindingLike, changed_files: set[str]) -> bool:
    refs = [finding.source_ref, *finding.evidence_refs]
    normalized_changed = {normalize_path(path) for path in changed_files}
    for ref in refs:
        if normalize_path(source_ref_path(ref)) in normalized_changed:
            return True
    return False


def is_pr_scoped_finding(finding: FindingLike, changed_files: set[str]) -> bool:
    if finding.rule_id.startswith(_PR_SCOPED_RULE_PREFIXES) or finding.rule_id in _PR_SCOPED_RULE_IDS:
        return True
    return bool(changed_files) and finding_matches_changed_files(finding, changed_files)
