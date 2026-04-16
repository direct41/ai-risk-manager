from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from ai_risk_manager.profiles.base import ProfileApplicability, ProfileId
from ai_risk_manager.signals.types import CapabilitySignal, SignalBundle

_SPEC_FILENAMES = (".riskmap.yml", ".riskmap.yaml")
_FLOW_FIELDS = {"match", "checks"}
_CHECK_TOKENS = {"check", "checks", "test", "tests", "spec", "smoke", "e2e", "playwright", "cypress", "__tests__"}
_NOISY_TOKENS = {
    "app",
    "apps",
    "src",
    "lib",
    "test",
    "tests",
    "spec",
    "smoke",
    "e2e",
    "unit",
    "integration",
    "page",
    "pages",
    "component",
    "components",
    "service",
    "services",
    "py",
    "js",
    "jsx",
    "ts",
    "tsx",
    "vue",
}


@dataclass
class BusinessInvariantPreparedProfile:
    profile_id: ProfileId
    applicability: ProfileApplicability
    spec_path: str | None = None


@dataclass(frozen=True)
class BusinessCriticalFlow:
    id: str
    match: tuple[str, ...]
    checks: tuple[str, ...]


@dataclass
class BusinessInvariantScopeAssessment:
    notes: list[str]
    signals: SignalBundle


def _find_spec(repo_path: Path) -> Path | None:
    for filename in _SPEC_FILENAMES:
        path = repo_path / filename
        if path.is_file():
            return path
    return None


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip()


def _clean_value(value: str) -> str:
    return value.strip().strip('"').strip("'").strip()


def _parse_values(raw_value: str) -> list[str]:
    raw_value = raw_value.strip()
    if not raw_value:
        return []
    if raw_value.startswith("[") and raw_value.endswith("]"):
        inner = raw_value[1:-1]
        return [cleaned for part in inner.split(",") if (cleaned := _clean_value(part))]
    return [cleaned] if (cleaned := _clean_value(raw_value)) else []


def _split_tokens(value: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9_]+", _normalize_path(value).lower()) if token}


def _expand_terms(values: list[str]) -> tuple[str, ...]:
    terms: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _normalize_path(value).lower().strip()
        candidates = [cleaned, *_split_tokens(cleaned)]
        for candidate in candidates:
            if not candidate or candidate in _NOISY_TOKENS or candidate in seen:
                continue
            terms.append(candidate)
            seen.add(candidate)
    return tuple(terms)


def _append_flow(raw: dict[str, list[str]], flows: list[BusinessCriticalFlow]) -> None:
    flow_id = next(iter(raw.get("id", [])), "").strip()
    if not flow_id:
        return
    match_terms = _expand_terms(raw.get("match", [])) or _expand_terms([flow_id])
    check_terms = _expand_terms(raw.get("checks", [])) or match_terms
    flows.append(BusinessCriticalFlow(id=flow_id, match=match_terms, checks=check_terms))


def _load_critical_flows(spec_path: Path) -> tuple[BusinessCriticalFlow, ...]:
    try:
        lines = spec_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return ()

    flows: list[BusinessCriticalFlow] = []
    current: dict[str, list[str]] | None = None
    in_critical_flows = False
    pending_field: str | None = None

    for raw_line in lines:
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        content = raw_line.strip()

        if indent == 0:
            if content.startswith("critical_flows:"):
                in_critical_flows = True
                pending_field = None
                continue
            if in_critical_flows:
                break
            continue

        if not in_critical_flows:
            continue

        if content.startswith("- "):
            item = content[2:].strip()
            if item.startswith("id:"):
                if current is not None:
                    _append_flow(current, flows)
                current = {"id": _parse_values(item.split(":", 1)[1])}
                pending_field = None
                continue
            if current is not None and pending_field is not None:
                current.setdefault(pending_field, []).extend(_parse_values(item))
            continue

        if current is None or ":" not in content:
            continue

        field, raw_value = content.split(":", 1)
        field = field.strip()
        if field not in _FLOW_FIELDS:
            pending_field = None
            continue

        values = _parse_values(raw_value)
        current.setdefault(field, []).extend(values)
        pending_field = field if not values else None

    if current is not None:
        _append_flow(current, flows)

    return tuple(flows)


def _matches_terms(path: str, terms: tuple[str, ...]) -> bool:
    normalized = _normalize_path(path).lower()
    path_tokens = _split_tokens(normalized)
    for term in terms:
        if "/" in term and term in normalized:
            return True
        if term in path_tokens:
            return True
        if len(term) >= 4 and term in normalized:
            return True
    return False


def _is_check_file(path: str) -> bool:
    normalized = _normalize_path(path).lower()
    path_tokens = _split_tokens(normalized)
    if path_tokens & _CHECK_TOKENS:
        return True
    name = Path(normalized).name
    return any(name.endswith(suffix) for suffix in (".test.py", ".spec.py", ".test.js", ".spec.js", ".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx"))


def _example_refs(paths: list[str], *, limit: int = 4) -> list[str]:
    return sorted(paths)[:limit]


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-z0-9_.-]+", "-", value.lower()).strip("-") or "flow"


class BusinessInvariantProfile:
    profile_id: ProfileId = "business_invariant_risk"

    def prepare(self, repo_path: Path, notes: list[str]) -> BusinessInvariantPreparedProfile:
        spec_path = _find_spec(repo_path)
        if spec_path is None:
            return BusinessInvariantPreparedProfile(profile_id=self.profile_id, applicability="not_applicable")

        relative_path = str(spec_path.relative_to(repo_path))
        notes.append(f"business_invariant_risk detected explicit invariant spec {relative_path}.")
        return BusinessInvariantPreparedProfile(
            profile_id=self.profile_id,
            applicability="partial",
            spec_path=relative_path,
        )

    def assess_changed_scope(
        self,
        prepared: BusinessInvariantPreparedProfile,
        repo_path: Path,
        changed_files: set[str] | None,
    ) -> BusinessInvariantScopeAssessment:
        if prepared.applicability == "not_applicable" or not prepared.spec_path or not changed_files:
            return BusinessInvariantScopeAssessment(notes=[], signals=SignalBundle())

        spec_path = repo_path / prepared.spec_path
        flows = _load_critical_flows(spec_path)
        if not flows:
            return BusinessInvariantScopeAssessment(
                notes=[f"business_invariant_risk found {prepared.spec_path} but no readable critical_flows entries."],
                signals=SignalBundle(),
            )

        normalized_changed = sorted({_normalize_path(path) for path in changed_files if _normalize_path(path)})
        check_files = [path for path in normalized_changed if _is_check_file(path)]
        implementation_files = [
            path
            for path in normalized_changed
            if path != prepared.spec_path and not _is_check_file(path)
        ]

        signals: list[CapabilitySignal] = []
        for flow in flows:
            matched_implementation = [path for path in implementation_files if _matches_terms(path, flow.match)]
            if not matched_implementation:
                continue

            matched_checks = [path for path in check_files if _matches_terms(path, flow.checks)]
            if matched_checks:
                continue

            evidence_refs = [*_example_refs(matched_implementation), prepared.spec_path]
            primary = evidence_refs[0]
            signals.append(
                CapabilitySignal(
                    id=f"sig:business-invariant:{_safe_id(flow.id)}:{primary}",
                    kind="business_invariant_risk",
                    source_ref=primary,
                    confidence="medium",
                    evidence_refs=evidence_refs,
                    attributes={
                        "issue_type": "critical_flow_changed_without_check_delta",
                        "flow_id": flow.id,
                        "changed_flow_file_count": str(len(matched_implementation)),
                        "example_files": ", ".join(_example_refs(matched_implementation)),
                        "check_terms": ", ".join(flow.checks),
                        "spec_path": prepared.spec_path,
                    },
                )
            )

        notes = [f"business_invariant_risk loaded {len(flows)} critical flow(s) from {prepared.spec_path}."]
        if signals:
            notes.append(f"business_invariant_risk produced {len(signals)} PR-scoped signal(s).")

        return BusinessInvariantScopeAssessment(
            notes=notes,
            signals=SignalBundle(
                signals=signals,
                supported_kinds={"business_invariant_risk"} if signals else set(),
            ),
        )


__all__ = [
    "BusinessCriticalFlow",
    "BusinessInvariantPreparedProfile",
    "BusinessInvariantProfile",
    "BusinessInvariantScopeAssessment",
]
