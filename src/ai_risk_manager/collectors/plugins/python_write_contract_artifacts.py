from __future__ import annotations

import ast
import re

_RAW_SQL_UPDATE_RE = re.compile(
    r"UPDATE\s+(?P<table>[A-Za-z_][A-Za-z0-9_]*)\s+SET[\s\S]*?WHERE\s+(?P<where>[\s\S]*?)(?:[\"'`]\s*[\),]|$)",
    re.IGNORECASE,
)
_QUERYSET_UPDATE_RE = re.compile(
    r"\.filter\((?P<filters>[\s\S]*?)\)\.(?:update|delete)\s*\(",
    re.IGNORECASE,
)
_CLIENT_FRESHNESS_RE = re.compile(
    r"\b(?:payload|data|request|body)\.(?:updated_at|version)\b|"
    r"\b(?:payload|data|request|body)\[['\"](?:updated_at|version)['\"]\]",
    re.IGNORECASE,
)
_ENTITY_FILTER_RE = re.compile(r"\b(?:id|pk|[A-Za-z_]+_id)\b", re.IGNORECASE)
_TENANT_GUARD_RE = re.compile(r"\b(?:user_id|tenant_id|account_id|org_id|organization_id)\b", re.IGNORECASE)
_FRESHNESS_GUARD_RE = re.compile(r"\b(?:updated_at|version)\b", re.IGNORECASE)
_FILTER_KWARG_RE = re.compile(r"\b(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=")


def _line_snippet(source_lines: list[str], line: int, *, window: int = 3) -> str:
    start = max(0, line - 1)
    end = min(len(source_lines), start + window)
    return "\n".join(part.rstrip() for part in source_lines[start:end]).strip()


def _qualname(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return ""
    parts = [node.name]
    current = parents.get(node)
    while current is not None:
        if isinstance(current, ast.ClassDef):
            parts.append(current.name)
        current = parents.get(current)
    return ".".join(reversed(parts))


def _line_from_offset(block: str, offset: int, start_line: int) -> int:
    return start_line + block.count("\n", 0, offset)


def _has_entity_filter(where_clause: str) -> bool:
    tokens = {token.lower() for token in _ENTITY_FILTER_RE.findall(where_clause)}
    entity_tokens = tokens - {"user_id", "tenant_id", "account_id", "org_id", "organization_id"}
    return bool(entity_tokens)


def _has_entity_filter_kwargs(filter_expr: str) -> bool:
    kwargs = {match.group("name").lower() for match in _FILTER_KWARG_RE.finditer(filter_expr)}
    entity_tokens = {
        name
        for name in kwargs
        if (name in {"id", "pk"} or name.endswith("_id"))
        and name not in {"user_id", "tenant_id", "account_id", "org_id", "organization_id"}
    }
    return bool(entity_tokens)


def extract_python_write_contract_issues(
    *,
    tree: ast.AST,
    source_lines: list[str],
    relative_path: str,
    owner_names: set[str],
) -> list[tuple[str, str, str, int | None, str, dict[str, str]]]:
    if not owner_names:
        return []

    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    issues: list[tuple[str, str, str, int | None, str, dict[str, str]]] = []
    seen: set[tuple[str, str, int]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        owner_name = _qualname(node, parents)
        if owner_name not in owner_names:
            continue
        start_line = getattr(node, "lineno", 1)
        end_line = getattr(node, "end_lineno", start_line)
        block = "\n".join(source_lines[start_line - 1 : end_line])
        lowered = block.lower()

        for match in _RAW_SQL_UPDATE_RE.finditer(block):
            where_clause = match.group("where")
            if _TENANT_GUARD_RE.search(where_clause) and not _has_entity_filter(where_clause):
                line = _line_from_offset(block, match.start(), start_line)
                marker = ("write_scope_missing_entity_filter", owner_name, line)
                if marker not in seen:
                    seen.add(marker)
                    issues.append(
                        (
                            relative_path,
                            "write_scope_missing_entity_filter",
                            owner_name,
                            line,
                            _line_snippet(source_lines, line),
                            {"missing_filter": "entity id"},
                        )
                    )
            if _CLIENT_FRESHNESS_RE.search(block) and not _FRESHNESS_GUARD_RE.search(where_clause):
                line = _line_from_offset(block, match.start(), start_line)
                marker = ("stale_write_without_conflict_guard", owner_name, line)
                if marker not in seen:
                    seen.add(marker)
                    issues.append(
                        (
                            relative_path,
                            "stale_write_without_conflict_guard",
                            owner_name,
                            line,
                            _line_snippet(source_lines, line),
                            {"guard_kind": "updated_at_or_version"},
                        )
                    )

        for match in _QUERYSET_UPDATE_RE.finditer(block):
            filters = match.group("filters")
            if _TENANT_GUARD_RE.search(filters) and not _has_entity_filter_kwargs(filters):
                line = _line_from_offset(block, match.start(), start_line)
                marker = ("write_scope_missing_entity_filter", owner_name, line)
                if marker not in seen:
                    seen.add(marker)
                    issues.append(
                        (
                            relative_path,
                            "write_scope_missing_entity_filter",
                            owner_name,
                            line,
                            _line_snippet(source_lines, line),
                            {"missing_filter": "entity id"},
                        )
                    )
            if _CLIENT_FRESHNESS_RE.search(lowered) and not _FRESHNESS_GUARD_RE.search(filters):
                line = _line_from_offset(block, match.start(), start_line)
                marker = ("stale_write_without_conflict_guard", owner_name, line)
                if marker not in seen:
                    seen.add(marker)
                    issues.append(
                        (
                            relative_path,
                            "stale_write_without_conflict_guard",
                            owner_name,
                            line,
                            _line_snippet(source_lines, line),
                            {"guard_kind": "updated_at_or_version"},
                        )
                    )

    return issues
