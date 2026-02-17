from __future__ import annotations

import ast
from dataclasses import dataclass, field
import os
from pathlib import Path

from ai_risk_manager.schemas.types import PreflightResult

WRITE_METHODS = ("post", "put", "patch", "delete")
ROUTE_METHODS = WRITE_METHODS + ("get",)
EXCLUDED_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".riskmap"}


@dataclass
class ArtifactBundle:
    all_files: list[Path] = field(default_factory=list)
    python_files: list[Path] = field(default_factory=list)
    write_endpoints: list[tuple[str, str]] = field(default_factory=list)  # (file, endpoint_name)
    test_files: list[Path] = field(default_factory=list)
    test_cases: list[tuple[str, str]] = field(default_factory=list)  # (file, test_function_name)


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


def _extract_write_endpoints(tree: ast.AST) -> list[str]:
    endpoints: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            is_router, method = _is_router_decorator(decorator)
            if is_router and method in WRITE_METHODS:
                endpoints.append(node.name)
                break
    return endpoints


def _extract_test_cases(tree: ast.AST) -> list[str]:
    cases: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            cases.append(node.name)
    return cases


def preflight_check(repo_path: Path) -> PreflightResult:
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

    reasons: list[str] = []
    if not has_fastapi_import and not has_router:
        reasons.append("FastAPI patterns were not found (imports/routes missing).")
        return PreflightResult(status="FAIL", reasons=reasons)

    if not has_pytest:
        reasons.append("pytest patterns were not found; test coverage recommendations may be noisy.")
        return PreflightResult(status="WARN", reasons=reasons)

    return PreflightResult(status="PASS", reasons=[])


def collect_artifacts(repo_path: Path) -> ArtifactBundle:
    bundle = ArtifactBundle()
    bundle.all_files = _iter_files(repo_path)
    bundle.python_files = [p for p in bundle.all_files if p.suffix == ".py"]
    bundle.test_files = [
        p
        for p in bundle.python_files
        if (
            (("tests" in p.parts) and p.name != "conftest.py" and (p.name.startswith("test_") or p.name.endswith("_test.py")))
            or p.name.startswith("test_")
            or p.name.endswith("_test.py")
        )
    ]

    for path in bundle.python_files:
        tree = _parse_ast(path)
        if tree is None:
            continue

        relative = path.relative_to(repo_path)
        for endpoint in _extract_write_endpoints(tree):
            bundle.write_endpoints.append((str(relative), endpoint))

        if path in bundle.test_files:
            for case in _extract_test_cases(tree):
                bundle.test_cases.append((str(relative), case))

    return bundle
