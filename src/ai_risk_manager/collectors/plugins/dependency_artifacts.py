from __future__ import annotations

import json
from pathlib import Path
import re
import tomllib

DependencySpecRow = tuple[str, str, str, int | None, str | None, str]

_DEPENDENCY_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+(?:\[[^\]]+\])?)\s*(.*)$")
_DEV_SCOPE_MARKERS = ("dev", "test", "lint", "docs", "qa", "type", "ci")
_SEMVER_EXACT_RE = re.compile(r"^v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
_NPM_DIRECT_REFERENCE_PREFIXES = ("git+", "git://", "github:", "http://", "https://", "file:", "link:", "workspace:")


def _clean_dependency_name(name: str) -> str:
    base = name.strip()
    if "[" in base:
        base = base.split("[", 1)[0]
    return base.strip().lower()


def _is_exact_version_pin(spec: str) -> bool:
    value = spec.strip()
    if not value:
        return False
    if value.startswith(("==", "===")):
        return "*" not in value
    return _SEMVER_EXACT_RE.fullmatch(value) is not None


def _dependency_policy_violation(raw_spec: str) -> str | None:
    spec = raw_spec.strip()
    if not spec:
        return "unpinned_version"
    if _is_exact_version_pin(spec):
        return None
    lowered = spec.lower()
    if any(lowered.startswith(prefix) for prefix in _NPM_DIRECT_REFERENCE_PREFIXES):
        return "direct_reference"
    if any(token in lowered for token in ("git+", "git://", "github:", "http://", "https://", "file:", "link:", "workspace:", " @ ")):
        return "direct_reference"
    if "*" in spec or re.search(r"(^|[.])x($|[.])", lowered):
        return "wildcard_version"
    if any(token in spec for token in (">", "<", "~=", "!=", ",", "^", "~", "||", " - ")):
        return "range_not_pinned"
    return "unpinned_version"


def _line_of_text_match(lines: list[str], target: str) -> int | None:
    needle = target.strip()
    if not needle:
        return None
    for idx, line in enumerate(lines, start=1):
        if needle in line:
            return idx
    return None


def _parse_dependency_entry(raw_entry: str) -> tuple[str, str] | None:
    entry = raw_entry.strip()
    if not entry:
        return None
    entry = entry.split(";", 1)[0].strip()
    if not entry:
        return None
    if " @ " in entry:
        name, ref = entry.split(" @ ", 1)
        dep_name = _clean_dependency_name(name)
        if dep_name:
            return dep_name, f"@ {ref.strip()}"
        return None
    match = _DEPENDENCY_LINE_RE.match(entry)
    if not match:
        return None
    dep_name = _clean_dependency_name(match.group(1))
    spec = match.group(2).strip()
    if not dep_name:
        return None
    return dep_name, spec


def _optional_group_scope(group: str) -> str:
    lowered = group.lower()
    if any(marker in lowered for marker in _DEV_SCOPE_MARKERS):
        return "development"
    return "runtime"


def _extract_pyproject_dependencies(repo_path: Path) -> list[DependencySpecRow]:
    path = repo_path / "pyproject.toml"
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        payload = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []

    project = payload.get("project")
    if not isinstance(project, dict):
        return []
    rows = project.get("dependencies")
    if not isinstance(rows, list):
        return []

    lines = text.splitlines()
    result: list[DependencySpecRow] = []
    for row in rows:
        if not isinstance(row, str):
            continue
        parsed = _parse_dependency_entry(row)
        if parsed is None:
            continue
        dep_name, spec = parsed
        result.append(
            (
                str(path.relative_to(repo_path)),
                dep_name,
                spec,
                _line_of_text_match(lines, row),
                _dependency_policy_violation(spec),
                "runtime",
            )
        )

    optional = project.get("optional-dependencies")
    if isinstance(optional, dict):
        for group_name, entries in optional.items():
            if not isinstance(group_name, str) or not isinstance(entries, list):
                continue
            scope = _optional_group_scope(group_name)
            for row in entries:
                if not isinstance(row, str):
                    continue
                parsed = _parse_dependency_entry(row)
                if parsed is None:
                    continue
                dep_name, spec = parsed
                result.append(
                    (
                        str(path.relative_to(repo_path)),
                        dep_name,
                        spec,
                        _line_of_text_match(lines, row),
                        _dependency_policy_violation(spec),
                        scope,
                    )
                )
    return result


def _parse_requirements_line(line: str) -> tuple[str, str] | None:
    row = line.strip()
    if not row or row.startswith("#"):
        return None
    if row.startswith(("-r", "--requirement", "-c", "--constraint", "-e", "--editable")):
        return None
    return _parse_dependency_entry(row)


def _requirements_scope(path: Path) -> str:
    lowered = path.name.lower()
    if any(marker in lowered for marker in _DEV_SCOPE_MARKERS):
        return "development"
    return "runtime"


def _extract_requirements_dependencies(repo_path: Path, all_files: list[Path]) -> list[DependencySpecRow]:
    candidates = [
        path
        for path in all_files
        if path.suffix == ".txt" and (path.name.startswith("requirements") or path.name.startswith("constraints"))
    ]
    result: list[DependencySpecRow] = []
    for path in candidates:
        scope = _requirements_scope(path)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for idx, line in enumerate(lines, start=1):
            parsed = _parse_requirements_line(line)
            if parsed is None:
                continue
            dep_name, spec = parsed
            result.append(
                (
                    str(path.relative_to(repo_path)),
                    dep_name,
                    spec,
                    idx,
                    _dependency_policy_violation(spec),
                    scope,
                )
            )
    return result


def _extract_package_json_dependencies(repo_path: Path) -> list[DependencySpecRow]:
    path = repo_path / "package.json"
    if not path.is_file():
        return []

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []

    lines = text.splitlines()
    result: list[DependencySpecRow] = []
    for field_name, scope in (("dependencies", "runtime"), ("devDependencies", "development")):
        field = payload.get(field_name)
        if not isinstance(field, dict):
            continue
        for raw_name, raw_spec in field.items():
            if not isinstance(raw_name, str) or not isinstance(raw_spec, str):
                continue
            dep_name = _clean_dependency_name(raw_name)
            result.append(
                (
                    str(path.relative_to(repo_path)),
                    dep_name,
                    raw_spec,
                    _line_of_text_match(lines, f'"{raw_name}"'),
                    _dependency_policy_violation(raw_spec),
                    scope,
                )
            )
    return result


def extract_dependency_specs(repo_path: Path, all_files: list[Path]) -> list[DependencySpecRow]:
    rows = _extract_pyproject_dependencies(repo_path)
    rows.extend(_extract_requirements_dependencies(repo_path, all_files))
    rows.extend(_extract_package_json_dependencies(repo_path))
    return rows
