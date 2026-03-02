from __future__ import annotations

import ast
from dataclasses import dataclass
import os
from pathlib import Path
import re

from ai_risk_manager.collectors.plugins.base import ArtifactBundle
from ai_risk_manager.collectors.plugins.dependency_artifacts import extract_dependency_specs

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
_VIEWSET_DEFAULT_WRITE_METHODS: dict[str, tuple[str, str]] = {
    "create": ("POST", ""),
    "update": ("PUT", "/{id}"),
    "partial_update": ("PATCH", "/{id}"),
    "destroy": ("DELETE", "/{id}"),
}


@dataclass
class DjangoSignals:
    has_django_import: bool
    has_drf_import: bool
    has_urlpatterns: bool
    has_pytest: bool


@dataclass
class RouterRegistration:
    router_var: str
    route_path: str
    view_ref: str
    basename: str | None


@dataclass
class ViewsetAction:
    endpoint_name: str
    method: str
    path_suffix: str
    line: int
    snippet: str


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


def _collect_string_aliases(node: ast.AST, *, base_aliases: dict[str, str] | None = None) -> dict[str, str]:
    aliases: dict[str, str] = dict(base_aliases or {})
    assignments = _iter_named_assignments(node)

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


def _iter_named_assignments(node: ast.AST) -> list[tuple[str, ast.AST]]:
    assignments: list[tuple[str, ast.AST]] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Assign):
            for target in child.targets:
                if isinstance(target, ast.Name):
                    assignments.append((target.id, child.value))
        elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name) and child.value is not None:
            assignments.append((child.target.id, child.value))
    return assignments


def _normalize_http_path(path: str) -> str | None:
    raw = path.strip()
    if not raw:
        return "/"
    raw = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^/]+", "", raw)
    raw = raw.split("?", 1)[0].split("#", 1)[0].strip()
    if not raw:
        return "/"
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


def _combine_paths(prefix: str, route: str) -> str | None:
    left = _normalize_django_route(prefix)
    right = _normalize_django_route(route)
    if left is None or right is None:
        return None
    if left == "/":
        return right
    if right == "/":
        return left
    return _normalize_http_path(f"{left}/{right.lstrip('/')}")


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


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _resolve_reverse_route(call: ast.Call, aliases: dict[str, str], route_name_map: dict[str, str]) -> str | None:
    route_name_expr: ast.AST | None = call.args[0] if call.args else None
    if route_name_expr is None:
        for kw in call.keywords:
            if kw.arg in {"viewname", "urlname"}:
                route_name_expr = kw.value
                break
    route_name = _resolve_string_expr(route_name_expr, aliases)
    if route_name is None:
        return None

    route = route_name_map.get(route_name)
    if route is None:
        return None

    kwargs_node: ast.AST | None = None
    for kw in call.keywords:
        if kw.arg == "kwargs":
            kwargs_node = kw.value
            break

    if isinstance(kwargs_node, ast.Dict):
        for key_node, value_node in zip(kwargs_node.keys, kwargs_node.values):
            key = _constant_str(key_node)
            value = _resolve_string_expr(value_node, aliases)
            if key and value is not None:
                route = route.replace("{" + key + "}", value)

    return route


def _resolve_test_route_expr(route_expr: ast.AST | None, aliases: dict[str, str], route_name_map: dict[str, str]) -> str | None:
    if route_expr is None:
        return None
    route = _resolve_string_expr(route_expr, aliases)
    if route is not None:
        return route

    if isinstance(route_expr, ast.Call) and _call_name(route_expr.func) == "reverse":
        return _resolve_reverse_route(route_expr, aliases, route_name_map)

    return None


def _collect_test_route_aliases(node: ast.AST, route_name_map: dict[str, str]) -> dict[str, str]:
    aliases = _collect_string_aliases(node)
    assignments = _iter_named_assignments(node)
    changed = True
    while changed:
        changed = False
        for name, value_node in assignments:
            if name in aliases:
                continue
            resolved = _resolve_test_route_expr(value_node, aliases, route_name_map)
            if resolved is None:
                continue
            aliases[name] = resolved
            changed = True
    return aliases


def _extract_test_http_calls(
    tree: ast.AST,
    source_lines: list[str],
    route_name_map: dict[str, str],
) -> list[tuple[str, str, str, int, str]]:
    calls: list[tuple[str, str, str, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith("test_"):
            continue
        aliases = _collect_test_route_aliases(node, route_name_map)
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
            route = _resolve_test_route_expr(route_expr, aliases, route_name_map)
            if route is None:
                continue
            normalized = _normalize_http_path(route)
            if normalized is None:
                continue

            line = getattr(child, "lineno", getattr(node, "lineno", 1))
            calls.append((node.name, method.upper(), normalized, line, _line_snippet(source_lines, line)))
    return calls


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


def _extract_router_var_from_include(node: ast.AST | None) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    if _call_name(node.func) != "include":
        return None
    if not node.args:
        return None

    arg = node.args[0]
    if isinstance(arg, ast.Attribute) and arg.attr == "urls" and isinstance(arg.value, ast.Name):
        return arg.value.id

    if isinstance(arg, ast.Tuple) and arg.elts:
        first = arg.elts[0]
        if isinstance(first, ast.Attribute) and first.attr == "urls" and isinstance(first.value, ast.Name):
            return first.value.id
    return None


def _extract_urlpatterns_data(tree: ast.AST) -> tuple[dict[str, list[str]], dict[str, str], dict[str, list[str]]]:
    route_map: dict[str, list[str]] = {}
    route_name_map: dict[str, str] = {}
    router_prefixes: dict[str, list[str]] = {}

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
            func_name = _call_name(elt.func)
            if func_name not in {"path", "re_path"}:
                continue

            route_raw = _constant_str(elt.args[0]) if elt.args else ""
            if route_raw is None:
                continue
            route_path = _normalize_django_route(route_raw)
            if route_path is None:
                continue

            route_name: str | None = None
            for kw in elt.keywords:
                if kw.arg == "name":
                    route_name = _constant_str(kw.value)
                    break
            if route_name:
                route_name_map[route_name] = route_path

            view_expr = elt.args[1] if len(elt.args) > 1 else None
            router_var = _extract_router_var_from_include(view_expr)
            if router_var is not None:
                router_prefixes.setdefault(router_var, []).append(route_path)
                continue

            view_ref = _resolve_view_ref(view_expr)
            if view_ref is None:
                continue
            route_map.setdefault(view_ref, []).append(route_path)

    return route_map, route_name_map, router_prefixes


def _is_api_view_decorator(node: ast.AST) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    return _call_name(target) == "api_view"


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
        base_name = _call_name(base)
        if base_name.endswith("APIView"):
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


def _is_viewset_class(node: ast.ClassDef) -> bool:
    for base in node.bases:
        base_name = _call_name(base)
        if base_name.endswith("ViewSet"):
            return True
    return False


def _extract_action_decorator_config(decorator: ast.AST) -> tuple[list[str], bool, str] | None:
    if not isinstance(decorator, ast.Call) or _call_name(decorator.func) != "action":
        return None

    methods: list[str] = []
    detail = False
    url_path: str | None = None

    for kw in decorator.keywords:
        if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
            methods = [str(value).upper() for value in (_constant_str(item) for item in kw.value.elts) if value]
        elif kw.arg == "detail" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, bool):
            detail = kw.value.value
        elif kw.arg == "url_path":
            url_path = _constant_str(kw.value)

    if not methods:
        return None

    return methods, detail, (url_path or "")


def _extract_viewset_actions(class_node: ast.ClassDef, source_lines: list[str]) -> list[ViewsetAction]:
    actions: list[ViewsetAction] = []
    for child in class_node.body:
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        method_name = child.name
        line = getattr(child, "lineno", getattr(class_node, "lineno", 1))
        snippet = _line_snippet(source_lines, line)

        if method_name in _VIEWSET_DEFAULT_WRITE_METHODS:
            http_method, suffix = _VIEWSET_DEFAULT_WRITE_METHODS[method_name]
            actions.append(
                ViewsetAction(
                    endpoint_name=f"{class_node.name}.{method_name}",
                    method=http_method,
                    path_suffix=suffix,
                    line=line,
                    snippet=snippet,
                )
            )
            continue

        for decorator in child.decorator_list:
            config = _extract_action_decorator_config(decorator)
            if config is None:
                continue
            methods, detail, url_path = config
            action_path = url_path or method_name.replace("_", "-")
            suffix = f"/{{id}}/{action_path}" if detail else f"/{action_path}"
            for method in methods:
                if method.lower() not in WRITE_METHODS:
                    continue
                actions.append(
                    ViewsetAction(
                        endpoint_name=f"{class_node.name}.{method_name}",
                        method=method,
                        path_suffix=suffix,
                        line=line,
                        snippet=snippet,
                    )
                )
    return actions


def _extract_router_registrations(tree: ast.AST) -> list[RouterRegistration]:
    registrations: list[RouterRegistration] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "register":
            continue
        if not isinstance(node.func.value, ast.Name):
            continue
        router_var = node.func.value.id

        route_raw = _constant_str(node.args[0]) if node.args else None
        if route_raw is None:
            continue
        route_path = _normalize_django_route(route_raw)
        if route_path is None:
            continue

        view_expr = node.args[1] if len(node.args) > 1 else None
        view_ref = _resolve_view_ref(view_expr)
        if view_ref is None:
            continue

        basename: str | None = None
        for kw in node.keywords:
            if kw.arg == "basename":
                basename = _constant_str(kw.value)
                break

        registrations.append(
            RouterRegistration(
                router_var=router_var,
                route_path=route_path,
                view_ref=view_ref,
                basename=basename,
            )
        )
    return registrations


def _registration_basename(registration: RouterRegistration) -> str:
    if registration.basename:
        return registration.basename
    token = registration.route_path.strip("/") or "resource"
    return token.replace("/", "-")


def _derive_route_name(path_suffix: str, basename: str) -> str | None:
    if path_suffix == "":
        return f"{basename}-list"
    if path_suffix == "/{id}":
        return f"{basename}-detail"

    token = path_suffix.strip("/")
    if token.startswith("{id}/"):
        token = token[len("{id}/") :]
    token = token.replace("/", "-")
    if not token:
        return None
    return f"{basename}-{token}"


def _extract_viewset_endpoints(
    parsed: list[tuple[Path, ast.AST, str, list[str]]],
    router_prefixes: dict[str, list[str]],
) -> tuple[list[tuple[str, str, str, str, int, str]], dict[str, str]]:
    registrations: list[RouterRegistration] = []
    class_index: dict[str, tuple[str, ast.ClassDef, list[str]]] = {}

    for _, tree, relative, source_lines in parsed:
        registrations.extend(_extract_router_registrations(tree))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and _is_viewset_class(node):
                class_index[node.name] = (relative, node, source_lines)

    endpoints: list[tuple[str, str, str, str, int, str]] = []
    route_name_map: dict[str, str] = {}
    for registration in registrations:
        class_meta = class_index.get(registration.view_ref)
        if class_meta is None:
            continue
        relative, class_node, source_lines = class_meta
        actions = _extract_viewset_actions(class_node, source_lines)
        if not actions:
            continue

        prefixes = router_prefixes.get(registration.router_var, ["/"])
        basename = _registration_basename(registration)
        for action in actions:
            for prefix in prefixes:
                base_route = _combine_paths(prefix, registration.route_path)
                if base_route is None:
                    continue
                full_route = _combine_paths(base_route, action.path_suffix)
                if full_route is None:
                    continue

                endpoints.append(
                    (
                        relative,
                        action.endpoint_name,
                        action.method,
                        full_route,
                        action.line,
                        action.snippet,
                    )
                )

                route_name = _derive_route_name(action.path_suffix, basename)
                if route_name is not None:
                    route_name_map[route_name] = full_route

    return endpoints, route_name_map


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
            route_map, _, router_prefixes = _extract_urlpatterns_data(tree)
            if route_map or router_prefixes:
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
    bundle.dependency_specs.extend(extract_dependency_specs(repo_path, bundle.all_files))
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
    route_name_map: dict[str, str] = {}
    router_prefixes: dict[str, list[str]] = {}
    for path, tree, _, _ in parsed:
        if path.name != "urls.py":
            continue
        local_route_map, local_route_name_map, local_router_prefixes = _extract_urlpatterns_data(tree)
        for view_ref, route_paths in local_route_map.items():
            route_map.setdefault(view_ref, []).extend(route_paths)
        route_name_map.update(local_route_name_map)
        for router_var, prefixes in local_router_prefixes.items():
            router_prefixes.setdefault(router_var, []).extend(prefixes)

    viewset_endpoints, viewset_route_names = _extract_viewset_endpoints(parsed, router_prefixes)
    route_name_map.update(viewset_route_names)
    bundle.write_endpoints.extend(viewset_endpoints)

    for path, tree, relative, source_lines in parsed:
        for endpoint_name, method, route_path, line, snippet in _extract_function_endpoints(tree, route_map, source_lines):
            bundle.write_endpoints.append((relative, endpoint_name, method, route_path, line, snippet))
        for endpoint_name, method, route_path, line, snippet in _extract_class_endpoints(tree, route_map, source_lines):
            bundle.write_endpoints.append((relative, endpoint_name, method, route_path, line, snippet))

        if path in bundle.test_files:
            for case, line, snippet in _extract_test_cases(tree, source_lines):
                bundle.test_cases.append((relative, case, line, snippet))
            for test_name, method, route_path, line, snippet in _extract_test_http_calls(tree, source_lines, route_name_map):
                bundle.test_http_calls.append((relative, test_name, method, route_path, line, snippet))

    return bundle


__all__ = ["DjangoSignals", "collect_django_artifacts", "scan_django_signals"]
