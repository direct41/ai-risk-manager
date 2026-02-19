from __future__ import annotations

import ast
from dataclasses import dataclass
import os
from pathlib import Path

from ai_risk_manager.collectors.plugins.base import ArtifactBundle, StackProbeResult
from ai_risk_manager.schemas.types import PreflightResult

WRITE_METHODS = ("post", "put", "patch", "delete")
ROUTE_METHODS = WRITE_METHODS + ("get",)
EXCLUDED_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".riskmap"}


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


def _extract_declared_transitions(tree: ast.AST) -> list[tuple[str, str, str]]:
    declared: list[tuple[str, str, str]] = []
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
                        declared.append((machine, src, dst))
            else:
                dst = _constant_str(value)
                if dst:
                    declared.append((machine, src, dst))
    return declared


def _extract_handled_transitions(tree: ast.AST) -> list[tuple[str, str, str]]:
    handled: list[tuple[str, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        fn_name = node.name
        for child in ast.walk(node):
            if not isinstance(child, ast.If):
                continue
            src_state: str | None = None
            status_var_name: str | None = None
            status_is_attr = False
            test = child.test
            if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq):
                left = test.left
                if isinstance(left, ast.Attribute) and left.attr == "status":
                    if test.comparators:
                        src_state = _constant_str(test.comparators[0])
                        status_is_attr = True
                if isinstance(left, ast.Name) and left.id == "status":
                    if test.comparators:
                        src_state = _constant_str(test.comparators[0])
                        status_var_name = left.id
            if not src_state:
                continue

            for stmt in ast.walk(child):
                if not isinstance(stmt, ast.Assign):
                    continue
                for target in stmt.targets:
                    if status_is_attr and isinstance(target, ast.Attribute) and target.attr == "status":
                        dst_state = _constant_str(stmt.value)
                        if dst_state:
                            handled.append((fn_name, src_state, dst_state))
                    if status_var_name and isinstance(target, ast.Name) and target.id == status_var_name:
                        dst_state = _constant_str(stmt.value)
                        if dst_state:
                            handled.append((fn_name, src_state, dst_state))
    return handled


def _extract_test_cases(tree: ast.AST) -> list[str]:
    cases: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            cases.append(node.name)
    return cases


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


def _probe_reasons(signals: FastAPISignals) -> list[str]:
    reasons: list[str] = []
    if signals.has_fastapi_import:
        reasons.append("Detected FastAPI import patterns.")
    if signals.has_router:
        reasons.append("Detected FastAPI router decorator patterns.")
    if signals.has_pytest:
        reasons.append("Detected pytest import patterns.")
    return reasons


def _preflight_from_signals(signals: FastAPISignals) -> PreflightResult:
    reasons: list[str] = []
    if not signals.has_fastapi_import and not signals.has_router:
        reasons.append("FastAPI patterns were not found (imports/routes missing).")
        return PreflightResult(status="FAIL", reasons=reasons)

    if not signals.has_pytest:
        reasons.append("pytest patterns were not found; test coverage recommendations may be noisy.")
        return PreflightResult(status="WARN", reasons=reasons)

    return PreflightResult(status="PASS", reasons=[])


class FastAPICollectorPlugin:
    stack_id = "fastapi_pytest"

    def probe(self, repo_path: Path) -> StackProbeResult | None:
        signals = scan_fastapi_signals(repo_path)
        if not signals.has_fastapi_import and not signals.has_router:
            return None

        confidence = "high" if signals.has_fastapi_import and signals.has_router else "medium"
        reasons = _probe_reasons(signals)
        if not signals.has_pytest:
            reasons.append("pytest patterns were not detected.")

        return StackProbeResult(
            stack_id=self.stack_id,
            confidence=confidence,
            reasons=reasons,
            probe_data=signals,
        )

    def preflight(self, repo_path: Path, probe_data: object | None = None) -> PreflightResult:
        signals = probe_data if isinstance(probe_data, FastAPISignals) else scan_fastapi_signals(repo_path)
        return _preflight_from_signals(signals)

    def collect(self, repo_path: Path) -> ArtifactBundle:
        bundle = ArtifactBundle()
        bundle.all_files = _iter_files(repo_path)
        bundle.python_files = [p for p in bundle.all_files if p.suffix == ".py"]
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

        parsed: list[tuple[Path, ast.AST, str]] = []
        for path in bundle.python_files:
            tree = _parse_ast(path)
            if tree is None:
                continue
            relative = str(path.relative_to(repo_path))
            parsed.append((path, tree, relative))

        for _, tree, relative in parsed:
            for model_name in _extract_pydantic_models(tree):
                bundle.pydantic_models.append((relative, model_name))

        known_models = {name for _, name in bundle.pydantic_models}

        for path, tree, relative in parsed:
            for endpoint in _extract_write_endpoints(tree):
                bundle.write_endpoints.append((relative, endpoint))

            for endpoint_name, model_name in _extract_endpoint_models(tree, known_models):
                bundle.endpoint_models.append((relative, endpoint_name, model_name))

            for machine, src, dst in _extract_declared_transitions(tree):
                bundle.declared_transitions.append((relative, machine, src, dst))

            for machine, src, dst in _extract_handled_transitions(tree):
                bundle.handled_transitions.append((relative, machine, src, dst))

            if path in bundle.test_files:
                for case in _extract_test_cases(tree):
                    bundle.test_cases.append((relative, case))

        return bundle
