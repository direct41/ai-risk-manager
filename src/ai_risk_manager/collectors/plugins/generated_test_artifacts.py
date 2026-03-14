from __future__ import annotations

import ast
from dataclasses import dataclass
import re
from typing import Callable

WRITE_METHODS = {"post", "put", "patch", "delete"}
_NEGATIVE_HTTP_CODES = {400, 401, 403, 404, 409, 410, 412, 422, 429, 500, 502, 503}
_JS_TEST_BLOCK_RE = re.compile(
    r"\b(?:test|it)\s*\(\s*(?P<quote>['\"`])(?P<name>[^'\"`]+)(?P=quote)\s*,\s*"
    r"(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][A-Za-z0-9_$]*)\s*=>\s*\{(?P<body>[\s\S]*?)\n\s*\}\s*\)\s*;?",
    re.IGNORECASE,
)
_JS_HTTP_CALL_RE = re.compile(
    r"\.(?P<method>post|put|patch|delete)\s*\(\s*(?P<quote>['\"`])(?P<path>[^'\"`]+)(?P=quote)",
    re.IGNORECASE,
)
_JS_NEGATIVE_ASSERT_RE = re.compile(
    r"(?:status\s*\(\s*(?:4\d\d|5\d\d)\s*\)|toBe\s*\(\s*(?:4\d\d|5\d\d)\s*\)|"
    r"rejects|toThrow|throw\s+new|unauthori[sz]ed|forbidden|invalid|conflict|not\s+found)",
    re.IGNORECASE,
)
_JS_NONDETERMINISTIC_PATTERNS: dict[str, re.Pattern[str]] = {
    "sleep": re.compile(r"\b(?:setTimeout|sleep)\s*\(", re.IGNORECASE),
    "time": re.compile(r"\b(?:Date\.now|new\s+Date\s*\()", re.IGNORECASE),
    "random": re.compile(r"\bMath\.random\s*\(", re.IGNORECASE),
    "network": re.compile(r"\b(?:fetch|axios\.(?:get|post|put|patch|delete)|httpx?\.)", re.IGNORECASE),
}


@dataclass
class TestQualityObservation:
    test_name: str
    line: int
    snippet: str
    http_calls: list[tuple[str, str]]
    has_negative_path: bool
    nondeterministic_kinds: set[str]


def _line_snippet(source_lines: list[str], line: int, *, window: int = 3) -> str:
    start = max(0, line - 1)
    end = min(len(source_lines), start + window)
    return "\n".join(part.rstrip() for part in source_lines[start:end]).strip()


def _line_from_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _constant_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _resolve_string_expr(node: ast.AST | None, aliases: dict[str, str]) -> str | None:
    if node is None:
        return None

    literal = _constant_str(node)
    if literal is not None:
        return literal

    if isinstance(node, ast.Name):
        return aliases.get(node.id)

    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
                continue
            if isinstance(value, ast.FormattedValue):
                inner = _resolve_string_expr(value.value, aliases)
                if inner is None:
                    return None
                parts.append(inner)
                continue
            return None
        return "".join(parts)

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _resolve_string_expr(node.left, aliases)
        right = _resolve_string_expr(node.right, aliases)
        if left is None or right is None:
            return None
        return f"{left}{right}"

    return None


def _collect_string_aliases(node: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    assignments: list[tuple[str, ast.AST]] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Assign):
            for target in child.targets:
                if isinstance(target, ast.Name):
                    assignments.append((target.id, child.value))
        elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name) and child.value is not None:
            assignments.append((child.target.id, child.value))

    changed = True
    while changed:
        changed = False
        for name, value_node in assignments:
            if name in aliases:
                continue
            resolved = _resolve_string_expr(value_node, aliases)
            if resolved is None:
                continue
            aliases[name] = resolved
            changed = True
    return aliases


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _call_root_name(node: ast.AST) -> str:
    current = node
    while isinstance(current, ast.Attribute):
        current = current.value
    if isinstance(current, ast.Name):
        return current.id
    return ""


def _has_negative_path_marker(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and _call_name(child.func) == "raises":
            return True
        if isinstance(child, ast.Constant) and isinstance(child.value, int) and child.value in _NEGATIVE_HTTP_CODES:
            return True
    return False


def _nondeterministic_kinds(node: ast.AST) -> set[str]:
    kinds: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func_name = _call_name(child.func).lower()
        root_name = _call_root_name(child.func).lower()

        if func_name == "sleep":
            kinds.add("sleep")
        if func_name in {"time", "time_ns", "monotonic", "perf_counter", "now", "utcnow", "today"}:
            kinds.add("time")
        if func_name in {"random", "randint", "randrange", "choice", "choices", "shuffle", "uniform"}:
            kinds.add("random")
        if root_name in {"requests", "httpx", "urllib", "urllib3"} and func_name in {
            "get",
            "post",
            "put",
            "patch",
            "delete",
            "request",
            "urlopen",
        }:
            kinds.add("network")
        if func_name == "urlopen":
            kinds.add("network")
    return kinds


def observe_python_test_quality(
    tree: ast.AST,
    source_lines: list[str],
    *,
    route_resolver: Callable[[ast.AST | None, dict[str, str]], str | None] | None = None,
) -> list[TestQualityObservation]:
    observations: list[TestQualityObservation] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith("test_"):
            continue

        aliases = _collect_string_aliases(node)
        http_calls: list[tuple[str, str]] = []
        for child in ast.walk(node):
            if not isinstance(child, ast.Call) or not isinstance(child.func, ast.Attribute):
                continue
            method = child.func.attr.lower()
            if method not in WRITE_METHODS:
                continue

            route_expr: ast.AST | None = child.args[0] if child.args else None
            if route_expr is None:
                for kw in child.keywords:
                    if kw.arg in {"path", "url"}:
                        route_expr = kw.value
                        break
            if route_resolver is not None:
                route = route_resolver(route_expr, aliases)
            else:
                route = _resolve_string_expr(route_expr, aliases)
            http_calls.append((method.upper(), route or ""))

        line = getattr(node, "lineno", 1)
        observations.append(
            TestQualityObservation(
                test_name=node.name,
                line=line,
                snippet=_line_snippet(source_lines, line),
                http_calls=http_calls,
                has_negative_path=_has_negative_path_marker(node),
                nondeterministic_kinds=_nondeterministic_kinds(node),
            )
        )
    return observations


def observe_js_test_quality(text: str, source_lines: list[str]) -> list[TestQualityObservation]:
    observations: list[TestQualityObservation] = []
    for match in _JS_TEST_BLOCK_RE.finditer(text):
        test_name = match.group("name").strip()
        body = match.group("body")
        line = _line_from_offset(text, match.start())
        http_calls = [
            (http_match.group("method").upper(), http_match.group("path").strip())
            for http_match in _JS_HTTP_CALL_RE.finditer(body)
        ]
        nondeterministic = {
            kind
            for kind, pattern in _JS_NONDETERMINISTIC_PATTERNS.items()
            if pattern.search(body)
        }
        observations.append(
            TestQualityObservation(
                test_name=test_name,
                line=line,
                snippet=_line_snippet(source_lines, line),
                http_calls=http_calls,
                has_negative_path=bool(_JS_NEGATIVE_ASSERT_RE.search(body)),
                nondeterministic_kinds=nondeterministic,
            )
        )
    return observations


def collect_generated_test_issues(
    *,
    relative_path: str,
    observations: list[TestQualityObservation],
) -> list[tuple[str, str, str, int | None, str, dict[str, str]]]:
    issues: list[tuple[str, str, str, int | None, str, dict[str, str]]] = []

    route_negative_coverage = {
        (method, path)
        for observation in observations
        if observation.has_negative_path
        for method, path in observation.http_calls
        if path
    }

    for observation in observations:
        for method, path in observation.http_calls:
            if observation.has_negative_path:
                continue
            if path and (method, path) in route_negative_coverage:
                continue
            issues.append(
                (
                    relative_path,
                    "missing_negative_path",
                    observation.test_name,
                    observation.line,
                    observation.snippet,
                    {
                        "test_name": observation.test_name,
                        "method": method,
                        "path": path,
                    },
                )
            )

        if observation.nondeterministic_kinds:
            issues.append(
                (
                    relative_path,
                    "nondeterministic_dependency",
                    observation.test_name,
                    observation.line,
                    observation.snippet,
                    {
                        "test_name": observation.test_name,
                        "dependency_kinds": ",".join(sorted(observation.nondeterministic_kinds)),
                    },
                )
            )

    return issues


__all__ = [
    "collect_generated_test_issues",
    "observe_js_test_quality",
    "observe_python_test_quality",
]
