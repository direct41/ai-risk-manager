from __future__ import annotations

import ast
from dataclasses import dataclass
import os
from pathlib import Path
import re

from ai_risk_manager.collectors.plugins.base import ArtifactBundle

WRITE_METHODS = ("post", "put", "patch", "delete")
ROUTE_METHODS = WRITE_METHODS + ("get",)
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".riskmap",
    "eval",
    "fixtures",
    "testdata",
}


@dataclass
class DjangoSignals:
    has_django_import: bool
    has_drf_import: bool
    has_urlpatterns: bool
    has_pytest: bool


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def _iter_files(repo_path: Path) -> list[Path]:
    files: list[Path] = []
    for root, dirs, filenames in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        root_path = Path(root)
        for filename in filenames:
            files.append(root_path / filename)
    return files


def _iter_python_files(repo_path: Path) -> list[Path]:
    return [p for p in _iter_files(repo_path) if p.suffix == ".py"]


def _line_snippet(source_lines: list[str], line: int, *, window: int = 3) -> str:
    start = max(0, line - 1)
    end = min(len(source_lines), start + window)
    return "\n".join(part.rstrip() for part in source_lines[start:end]).strip()


def _constant_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _resolve_string_expr(node: ast.AST | None, aliases: dict[str, str]) -> str | None:
    if node is None:
        return None

    const = _constant_str(node)
    if const is not None:
        return const

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
                parts.append(inner if inner is not None else "{param}")
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


def _normalize_http_path(path: str) -> str | None:
    raw = path.strip()
    if not raw:
        return None
    raw = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^/]+", "", raw)
    raw = raw.split("?", 1)[0].split("#", 1)[0].strip()
    if not raw:
        return None
    if not raw.startswith("/"):
        raw = f"/{raw}"
    raw = re.sub(r"/{2,}", "/", raw)
    if len(raw) > 1:
        raw = raw.rstrip("/")
    return raw


def _normalize_django_route(route: str) -> str | None:
    normalized = _normalize_http_path(route)
    if normalized is None:
        return None
    # Django path params: <str:id> / <id> -> {id}
    normalized = re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", normalized)
    return normalized


def _is_test_file(path: Path) -> bool:
    return (
        (("tests" in path.parts) and path.name != "conftest.py" and (path.name.startswith("test_") or path.name.endswith("_test.py")))
        or path.name.startswith("test_")
        or path.name.endswith("_test.py")
    )


def _extract_test_cases(tree: ast.AST, source_lines: list[str]) -> list[tuple[str, int, str]]:
    cases: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            line = getattr(node, "lineno", 1)
            cases.append((node.name, line, _line_snippet(source_lines, line)))
    return cases


def _extract_test_http_calls(tree: ast.AST, source_lines: list[str]) -> list[tuple[str, str, str, int, str]]:
    calls: list[tuple[str, str, str, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith("test_"):
            continue
        aliases = _collect_string_aliases(node)
        for child in ast.walk(node):
            if not isinstance(child, ast.Call) or not isinstance(child.func, ast.Attribute):
                continue
            method = child.func.attr.lower()
            if method not in ROUTE_METHODS:
                continue

            route_expr: ast.AST | None = child.args[0] if child.args else None
            if route_expr is None:
                for kw in child.keywords:
                    if kw.arg in {"path", "url"}:
                        route_expr = kw.value
                        break
            route = _resolve_string_expr(route_expr, aliases)
            if route is None:
                continue
            normalized = _normalize_http_path(route)
            if normalized is None:
                continue

            line = getattr(child, "lineno", getattr(node, "lineno", 1))
            calls.append((node.name, method.upper(), normalized, line, _line_snippet(source_lines, line)))
    return calls


def _extract_urlpatterns_route_map(tree: ast.AST) -> dict[str, list[str]]:
    route_map: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not node.targets:
            continue
        if not any(isinstance(target, ast.Name) and target.id == "urlpatterns" for target in node.targets):
            continue
        if not isinstance(node.value, (ast.List, ast.Tuple)):
            continue

        for elt in node.value.elts:
            if not isinstance(elt, ast.Call):
                continue
            func = elt.func
            func_name = ""
            if isinstance(func, ast.Name):
                func_name = func.id
            elif isinstance(func, ast.Attribute):
                func_name = func.attr
            if func_name not in {"path", "re_path"}:
                continue

            route_raw = _constant_str(elt.args[0]) if elt.args else None
            if route_raw is None:
                continue
            route_path = _normalize_django_route(route_raw)
            if route_path is None:
                continue

            view_expr = elt.args[1] if len(elt.args) > 1 else None
            view_ref = _resolve_view_ref(view_expr)
            if view_ref is None:
                continue
            route_map.setdefault(view_ref, []).append(route_path)
    return route_map


def _resolve_view_ref(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "as_view":
        base = node.func.value
        if isinstance(base, ast.Name):
            return base.id
        if isinstance(base, ast.Attribute):
            return base.attr
    return None


def _is_api_view_decorator(node: ast.AST) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Name):
        return target.id == "api_view"
    if isinstance(target, ast.Attribute):
        return target.attr == "api_view"
    return False


def _extract_api_view_methods(decorator: ast.AST) -> list[str]:
    if not isinstance(decorator, ast.Call) or not _is_api_view_decorator(decorator):
        return []
    if not decorator.args or not isinstance(decorator.args[0], (ast.List, ast.Tuple)):
        return []
    methods: list[str] = []
    for elt in decorator.args[0].elts:
        value = _constant_str(elt)
        if value:
            methods.append(value.upper())
    return methods


def _extract_function_endpoints(
    tree: ast.AST,
    route_map: dict[str, list[str]],
    source_lines: list[str],
) -> list[tuple[str, str, str, int, str]]:
    endpoints: list[tuple[str, str, str, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        methods: set[str] = set()
        for decorator in node.decorator_list:
            methods.update(_extract_api_view_methods(decorator))
        write_methods = [method for method in methods if method.lower() in WRITE_METHODS]
        if not write_methods:
            continue

        route_paths = route_map.get(node.name, [])
        for method in sorted(write_methods):
            for route_path in route_paths:
                line = getattr(node, "lineno", 1)
                endpoints.append((node.name, method.upper(), route_path, line, _line_snippet(source_lines, line)))
    return endpoints


def _is_api_view_class(node: ast.ClassDef) -> bool:
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id.endswith("APIView"):
            return True
        if isinstance(base, ast.Attribute) and base.attr.endswith("APIView"):
            return True
    return False


def _extract_class_endpoints(
    tree: ast.AST,
    route_map: dict[str, list[str]],
    source_lines: list[str],
) -> list[tuple[str, str, str, int, str]]:
    endpoints: list[tuple[str, str, str, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or not _is_api_view_class(node):
            continue
        route_paths = route_map.get(node.name, [])
        if not route_paths:
            continue
        for child in node.body:
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            method = child.name.lower()
            if method not in WRITE_METHODS:
                continue
            line = getattr(child, "lineno", getattr(node, "lineno", 1))
            endpoint_name = f"{node.name}.{child.name}"
            for route_path in route_paths:
                endpoints.append((endpoint_name, method.upper(), route_path, line, _line_snippet(source_lines, line)))
    return endpoints


def scan_django_signals(repo_path: Path) -> DjangoSignals:
    has_django_import = False
    has_drf_import = False
    has_urlpatterns = False
    has_pytest = False
    for path in _iter_python_files(repo_path):
        text = _read_text(path)
        if not text:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue

        if path.name == "urls.py":
            route_map = _extract_urlpatterns_route_map(tree)
            if route_map:
                has_urlpatterns = True

        for node in ast.walk(tree):
            if not has_django_import and isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith("django"):
                    has_django_import = True
                if module.startswith("rest_framework"):
                    has_drf_import = True
                if module.startswith("pytest"):
                    has_pytest = True
            if not has_django_import and isinstance(node, ast.Import):
                has_django_import = any(alias.name.startswith("django") for alias in node.names)
                has_drf_import = has_drf_import or any(alias.name.startswith("rest_framework") for alias in node.names)
                has_pytest = has_pytest or any(alias.name.startswith("pytest") for alias in node.names)
            if not has_pytest and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                has_pytest = True

    return DjangoSignals(
        has_django_import=has_django_import,
        has_drf_import=has_drf_import,
        has_urlpatterns=has_urlpatterns,
        has_pytest=has_pytest,
    )


def collect_django_artifacts(repo_path: Path) -> ArtifactBundle:
    bundle = ArtifactBundle()
    bundle.all_files = _iter_files(repo_path)
    bundle.python_files = [path for path in bundle.all_files if path.suffix == ".py"]
    bundle.test_files = [path for path in bundle.python_files if _is_test_file(path)]

    parsed: list[tuple[Path, ast.AST, str, list[str]]] = []
    for path in bundle.python_files:
        text = _read_text(path)
        if not text:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        relative = str(path.relative_to(repo_path))
        parsed.append((path, tree, relative, text.splitlines()))

    route_map: dict[str, list[str]] = {}
    for path, tree, _, _ in parsed:
        if path.name != "urls.py":
            continue
        for view_ref, route_paths in _extract_urlpatterns_route_map(tree).items():
            route_map.setdefault(view_ref, []).extend(route_paths)

    for path, tree, relative, source_lines in parsed:
        for endpoint_name, method, route_path, line, snippet in _extract_function_endpoints(tree, route_map, source_lines):
            bundle.write_endpoints.append((relative, endpoint_name, method, route_path, line, snippet))
        for endpoint_name, method, route_path, line, snippet in _extract_class_endpoints(tree, route_map, source_lines):
            bundle.write_endpoints.append((relative, endpoint_name, method, route_path, line, snippet))

        if path in bundle.test_files:
            for case, line, snippet in _extract_test_cases(tree, source_lines):
                bundle.test_cases.append((relative, case, line, snippet))
            for test_name, method, route_path, line, snippet in _extract_test_http_calls(tree, source_lines):
                bundle.test_http_calls.append((relative, test_name, method, route_path, line, snippet))

    return bundle


__all__ = ["DjangoSignals", "collect_django_artifacts", "scan_django_signals"]
