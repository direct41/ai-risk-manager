from __future__ import annotations

import ast
from dataclasses import dataclass
import os
from pathlib import Path
import re
import tomllib

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
GUARD_HINTS = (
    "allow",
    "valid",
    "invariant",
    "guard",
    "check",
    "ensure",
    "verify",
    "auth",
    "permission",
    "can_",
    "policy",
    "transition",
)
DEPENDENCY_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+(?:\[[^\]]+\])?)\s*(.*)$")
DEV_SCOPE_MARKERS = ("dev", "test", "lint", "docs", "qa", "type", "ci")


@dataclass
class FastAPISignals:
    has_fastapi_import: bool
    has_router: bool
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


def _parse_ast(path: Path) -> ast.AST | None:
    text = _read_text(path)
    if not text:
        return None
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def _line_snippet(source_lines: list[str], line: int, *, window: int = 3) -> str:
    start = max(0, line - 1)
    end = min(len(source_lines), start + window)
    return "\n".join(part.rstrip() for part in source_lines[start:end]).strip()


def _decorator_route_path(decorator: ast.AST) -> str | None:
    if not isinstance(decorator, ast.Call):
        return None
    if decorator.args:
        first = _constant_str(decorator.args[0])
        if first:
            return first
    for kw in decorator.keywords:
        if kw.arg in {"path", "url"}:
            value = _constant_str(kw.value)
            if value:
                return value
    return None


def _is_router_decorator(decorator: ast.AST) -> tuple[bool, str]:
    node = decorator
    if isinstance(node, ast.Call):
        node = node.func
    if not isinstance(node, ast.Attribute):
        return False, ""
    method = node.attr.lower()
    is_router = _has_router_anchor(node.value)
    return is_router and method in ROUTE_METHODS, method


def _has_router_anchor(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id.lower().endswith("router")
    if isinstance(node, ast.Attribute):
        if node.attr.lower().endswith("router"):
            return True
        return _has_router_anchor(node.value)
    return False


def _extract_write_endpoints(tree: ast.AST, source_lines: list[str]) -> list[tuple[str, str, str, int, str]]:
    endpoints: list[tuple[str, str, str, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            is_router, method = _is_router_decorator(decorator)
            if is_router and method in WRITE_METHODS:
                route_path = _decorator_route_path(decorator) or f"/{node.name}"
                line = getattr(node, "lineno", 1)
                endpoints.append((node.name, method.upper(), route_path, line, _line_snippet(source_lines, line)))
                break
    return endpoints


def _is_basemodel_subclass(node: ast.ClassDef) -> bool:
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == "BaseModel":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "BaseModel":
            return True
    return False


def _extract_pydantic_models(tree: ast.AST) -> list[str]:
    models: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and _is_basemodel_subclass(node):
            models.append(node.name)
    return models


def _annotation_name(annotation: ast.AST | None) -> str | None:
    if annotation is None:
        return None
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Attribute):
        return annotation.attr
    if isinstance(annotation, ast.Subscript):
        return _annotation_name(annotation.value)
    return None


def _decorator_response_model(decorator: ast.AST) -> str | None:
    node = decorator
    if not isinstance(node, ast.Call):
        return None
    for kw in node.keywords:
        if kw.arg == "response_model":
            return _annotation_name(kw.value)
    return None


def _extract_endpoint_models(tree: ast.AST, known_models: set[str]) -> list[tuple[str, str]]:
    endpoint_models: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        is_endpoint = False
        response_models: set[str] = set()
        for decorator in node.decorator_list:
            ok, _ = _is_router_decorator(decorator)
            if ok:
                is_endpoint = True
                response_model = _decorator_response_model(decorator)
                if response_model and response_model in known_models:
                    response_models.add(response_model)

        if not is_endpoint:
            continue

        for arg in node.args.args:
            model_name = _annotation_name(arg.annotation)
            if model_name and model_name in known_models:
                endpoint_models.append((node.name, model_name))

        for model_name in response_models:
            endpoint_models.append((node.name, model_name))

    return endpoint_models


def _constant_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _extract_declared_transitions(tree: ast.AST, source_lines: list[str]) -> list[tuple[str, str, str, int, str]]:
    declared: list[tuple[str, str, str, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        if not node.targets:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        target_name = target.id.lower()
        if "transition" not in target_name:
            continue
        machine = target.id

        for key, value in zip(node.value.keys, node.value.values):
            src = _constant_str(key)
            if not src:
                continue
            if isinstance(value, (ast.List, ast.Tuple)):
                for elt in value.elts:
                    dst = _constant_str(elt)
                    if dst:
                        line = getattr(node, "lineno", 1)
                        declared.append((machine, src, dst, line, _line_snippet(source_lines, line)))
            else:
                dst = _constant_str(value)
                if dst:
                    line = getattr(node, "lineno", 1)
                    declared.append((machine, src, dst, line, _line_snippet(source_lines, line)))
    return declared


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id.lower()
    if isinstance(node.func, ast.Attribute):
        return node.func.attr.lower()
    return ""


def _has_guard_hint(value: str) -> bool:
    normalized = value.lower()
    return any(hint in normalized for hint in GUARD_HINTS)


def _looks_like_guard_expr(expr: ast.AST) -> bool:
    for node in ast.walk(expr):
        if isinstance(node, ast.Name) and _has_guard_hint(node.id):
            return True
        if isinstance(node, ast.Attribute) and _has_guard_hint(node.attr):
            return True
        if isinstance(node, ast.Call):
            call_name = _call_name(node)
            if call_name and _has_guard_hint(call_name):
                return True
    return False


def _extract_status_source(test: ast.AST) -> tuple[str | None, str | None, bool]:
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And):
        for value in test.values:
            src_state, status_var_name, status_is_attr = _extract_status_source(value)
            if src_state:
                return src_state, status_var_name, status_is_attr
        return None, None, False

    if not (isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)):
        return None, None, False
    if not test.comparators:
        return None, None, False

    src_state = _constant_str(test.comparators[0])
    if not src_state:
        return None, None, False
    left = test.left
    if isinstance(left, ast.Attribute) and left.attr == "status":
        return src_state, None, True
    if isinstance(left, ast.Name) and left.id == "status":
        return src_state, left.id, False
    return None, None, False


def _has_additional_guard_in_test(test: ast.AST) -> bool:
    if not (isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And)):
        return False
    for value in test.values:
        src_state, _, _ = _extract_status_source(value)
        if src_state:
            continue
        if _looks_like_guard_expr(value):
            return True
    return False


def _collect_guard_lines(node: ast.AST) -> set[int]:
    lines: set[int] = set()
    for child in ast.walk(node):
        line = getattr(child, "lineno", None)
        if line is None:
            continue
        if isinstance(child, ast.Assert):
            lines.add(line)
            continue
        if isinstance(child, ast.If) and _looks_like_guard_expr(child.test):
            lines.add(line)
            continue
        if isinstance(child, ast.Expr) and isinstance(child.value, ast.Call):
            if _has_guard_hint(_call_name(child.value)):
                lines.add(line)
    return lines


def _extract_handled_transitions(tree: ast.AST, source_lines: list[str]) -> list[tuple[str, str, str, int, str, bool]]:
    handled: list[tuple[str, str, str, int, str, bool]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        fn_name = node.name
        function_guard_lines = _collect_guard_lines(node)
        for child in ast.walk(node):
            if not isinstance(child, ast.If):
                continue
            src_state, status_var_name, status_is_attr = _extract_status_source(child.test)
            if not src_state:
                continue

            branch_guard_lines = _collect_guard_lines(child)
            guard_lines = function_guard_lines | branch_guard_lines
            has_test_guard = _has_additional_guard_in_test(child.test)
            for stmt in ast.walk(child):
                if not isinstance(stmt, ast.Assign):
                    continue
                for target in stmt.targets:
                    if status_is_attr and isinstance(target, ast.Attribute) and target.attr == "status":
                        dst_state = _constant_str(stmt.value)
                        if dst_state:
                            line = getattr(stmt, "lineno", getattr(node, "lineno", 1))
                            invariant_guarded = has_test_guard or any(guard_line < line for guard_line in guard_lines)
                            handled.append(
                                (fn_name, src_state, dst_state, line, _line_snippet(source_lines, line), invariant_guarded)
                            )
                    if status_var_name and isinstance(target, ast.Name) and target.id == status_var_name:
                        dst_state = _constant_str(stmt.value)
                        if dst_state:
                            line = getattr(stmt, "lineno", getattr(node, "lineno", 1))
                            invariant_guarded = has_test_guard or any(guard_line < line for guard_line in guard_lines)
                            handled.append(
                                (fn_name, src_state, dst_state, line, _line_snippet(source_lines, line), invariant_guarded)
                            )
    return handled


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
        test_name = node.name
        for child in ast.walk(node):
            if not isinstance(child, ast.Call) or not isinstance(child.func, ast.Attribute):
                continue
            method = child.func.attr.lower()
            if method not in ROUTE_METHODS:
                continue

            route_path: str | None = None
            if child.args:
                route_path = _constant_str(child.args[0])
            if route_path is None:
                for kw in child.keywords:
                    if kw.arg in {"path", "url"}:
                        route_path = _constant_str(kw.value)
                        if route_path is not None:
                            break
            if route_path is None:
                continue

            line = getattr(child, "lineno", getattr(node, "lineno", 1))
            calls.append((test_name, method.upper(), route_path, line, _line_snippet(source_lines, line)))
    return calls


def _clean_dependency_name(name: str) -> str:
    base = name.strip()
    if "[" in base:
        base = base.split("[", 1)[0]
    return base.strip().lower()


def _dependency_policy_violation(raw_spec: str) -> str | None:
    spec = raw_spec.strip()
    if not spec:
        return "unpinned_version"
    lowered = spec.lower()
    if any(token in lowered for token in ("git+", "http://", "https://", "file:", " @ ")):
        return "direct_reference"
    if "==" in spec or "===" in spec:
        if "*" in spec:
            return "wildcard_version"
        return None
    if any(token in spec for token in (">", "<", "~=", "!=", ",")):
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
    match = DEPENDENCY_LINE_RE.match(entry)
    if not match:
        return None
    dep_name = _clean_dependency_name(match.group(1))
    spec = match.group(2).strip()
    if not dep_name:
        return None
    return dep_name, spec


def _optional_group_scope(group: str) -> str:
    lowered = group.lower()
    if any(marker in lowered for marker in DEV_SCOPE_MARKERS):
        return "development"
    return "runtime"


def _extract_pyproject_dependencies(repo_path: Path) -> list[tuple[str, str, str, int | None, str | None, str]]:
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
    result: list[tuple[str, str, str, int | None, str | None, str]] = []
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
    if any(marker in lowered for marker in DEV_SCOPE_MARKERS):
        return "development"
    return "runtime"


def _extract_requirements_dependencies(
    repo_path: Path, all_files: list[Path]
) -> list[tuple[str, str, str, int | None, str | None, str]]:
    candidates = [
        path
        for path in all_files
        if path.suffix == ".txt" and (path.name.startswith("requirements") or path.name.startswith("constraints"))
    ]
    result: list[tuple[str, str, str, int | None, str | None, str]] = []
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


def scan_fastapi_signals(repo_path: Path) -> FastAPISignals:
    py_files = _iter_python_files(repo_path)
    has_fastapi_import = False
    has_router = False
    has_pytest = False

    for path in py_files:
        tree = _parse_ast(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not has_fastapi_import and isinstance(node, ast.ImportFrom) and (node.module or "").startswith("fastapi"):
                has_fastapi_import = True
            if not has_fastapi_import and isinstance(node, ast.Import):
                has_fastapi_import = any(alias.name.startswith("fastapi") for alias in node.names)
            if not has_pytest and isinstance(node, ast.ImportFrom) and (node.module or "").startswith("pytest"):
                has_pytest = True
            if not has_pytest and isinstance(node, ast.Import):
                has_pytest = any(alias.name.startswith("pytest") for alias in node.names)
            if not has_router and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    is_router, _ = _is_router_decorator(decorator)
                    if is_router:
                        has_router = True
                        break
            if has_fastapi_import and has_router and has_pytest:
                break

    return FastAPISignals(
        has_fastapi_import=has_fastapi_import,
        has_router=has_router,
        has_pytest=has_pytest,
    )


def collect_fastapi_artifacts(repo_path: Path) -> ArtifactBundle:
    bundle = ArtifactBundle()
    bundle.all_files = _iter_files(repo_path)
    bundle.python_files = [p for p in bundle.all_files if p.suffix == ".py"]
    bundle.dependency_specs.extend(_extract_pyproject_dependencies(repo_path))
    bundle.dependency_specs.extend(_extract_requirements_dependencies(repo_path, bundle.all_files))
    bundle.test_files = [
        p
        for p in bundle.python_files
        if (
            (
                ("tests" in p.parts)
                and p.name != "conftest.py"
                and (p.name.startswith("test_") or p.name.endswith("_test.py"))
            )
            or p.name.startswith("test_")
            or p.name.endswith("_test.py")
        )
    ]

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

    for _, tree, relative, _ in parsed:
        for model_name in _extract_pydantic_models(tree):
            bundle.pydantic_models.append((relative, model_name))

    known_models = {name for _, name in bundle.pydantic_models}

    for path, tree, relative, source_lines in parsed:
        for endpoint_name, method, route_path, line, snippet in _extract_write_endpoints(tree, source_lines):
            bundle.write_endpoints.append((relative, endpoint_name, method, route_path, line, snippet))

        for endpoint_name, model_name in _extract_endpoint_models(tree, known_models):
            bundle.endpoint_models.append((relative, endpoint_name, model_name))

        for machine, src, dst, line, snippet in _extract_declared_transitions(tree, source_lines):
            bundle.declared_transitions.append((relative, machine, src, dst, line, snippet))

        for machine, src, dst, line, snippet, invariant_guarded in _extract_handled_transitions(tree, source_lines):
            bundle.handled_transitions.append((relative, machine, src, dst, line, snippet, invariant_guarded))

        if path in bundle.test_files:
            for case, line, snippet in _extract_test_cases(tree, source_lines):
                bundle.test_cases.append((relative, case, line, snippet))
            for test_name, method, route_path, line, snippet in _extract_test_http_calls(tree, source_lines):
                bundle.test_http_calls.append((relative, test_name, method, route_path, line, snippet))

    return bundle


__all__ = ["FastAPISignals", "collect_fastapi_artifacts", "scan_fastapi_signals"]
