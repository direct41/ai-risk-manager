from __future__ import annotations

import ast
import os
from pathlib import Path

from ai_risk_manager.collectors.plugins.base import ArtifactBundle
from ai_risk_manager.collectors.plugins.dependency_artifacts import extract_dependency_specs
from ai_risk_manager.collectors.plugins.generated_test_artifacts import (
    collect_generated_test_issues,
    observe_js_test_quality,
    observe_python_test_quality,
)
from ai_risk_manager.collectors.plugins.workflow_automation_artifacts import collect_workflow_automation_issues

_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".riskmap",
    "dist",
    "build",
    "coverage",
    "eval",
    "fixtures",
    "testdata",
}
_JS_TEST_SUFFIXES = {".js", ".jsx", ".cjs", ".mjs", ".ts", ".tsx"}


def _iter_files(repo_path: Path) -> list[Path]:
    files: list[Path] = []
    for root, dirs, filenames in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in _EXCLUDED_DIRS]
        root_path = Path(root)
        for filename in filenames:
            files.append(root_path / filename)
    return files


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _parse_python_ast(text: str) -> ast.AST | None:
    if not text:
        return None
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def _is_test_file(path: Path) -> bool:
    lowered_name = path.name.lower()
    lowered_parts = {part.lower() for part in path.parts}
    return (
        lowered_name.startswith("test_")
        or lowered_name.endswith(("_test.py", ".test.js", ".spec.js", ".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx"))
        or "__tests__" in lowered_parts
        or "tests" in lowered_parts
        or "test" in lowered_parts
    )


def collect_universal_artifacts(repo_path: Path) -> ArtifactBundle:
    all_files = _iter_files(repo_path)
    bundle = ArtifactBundle(
        all_files=all_files,
        python_files=[path for path in all_files if path.suffix.lower() == ".py"],
        test_files=[path for path in all_files if _is_test_file(path)],
    )
    bundle.dependency_specs.extend(extract_dependency_specs(repo_path, all_files))
    bundle.workflow_automation_issues.extend(collect_workflow_automation_issues(repo_path, all_files))

    for path in bundle.test_files:
        relative_path = str(path.relative_to(repo_path))
        text = _read_text(path)
        if not text:
            continue
        source_lines = text.splitlines()
        observations = []
        if path.suffix.lower() == ".py":
            tree = _parse_python_ast(text)
            if tree is None:
                continue
            observations = observe_python_test_quality(tree, source_lines)
        elif path.suffix.lower() in _JS_TEST_SUFFIXES:
            observations = observe_js_test_quality(text, source_lines)
        if not observations:
            continue
        bundle.generated_test_issues.extend(
            collect_generated_test_issues(relative_path=relative_path, observations=observations)
        )

    return bundle


__all__ = ["collect_universal_artifacts"]
