from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re

from ai_risk_manager.collectors.plugins.base import ArtifactBundle
from ai_risk_manager.collectors.plugins.dependency_artifacts import extract_dependency_specs

WRITE_METHODS = ("post", "put", "patch", "delete")
JS_SUFFIXES = {".js", ".cjs", ".mjs", ".ts", ".tsx"}
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
    "dist",
    "build",
    "coverage",
}
_EXPRESS_IMPORT_RE = re.compile(r"(?:require\(\s*['\"]express['\"]\s*\))|(?:from\s+['\"]express['\"])", re.IGNORECASE)
_ROUTE_CALL_RE = re.compile(
    r"\b(?P<receiver>[A-Za-z_$][A-Za-z0-9_$]*)\.(?P<method>post|put|patch|delete)\s*\(\s*"
    r"(?P<quote>['\"`])(?P<path>[^'\"`]+)(?P=quote)\s*(?:,\s*(?P<handler>[A-Za-z_$][A-Za-z0-9_$]*))?",
    re.IGNORECASE,
)
_TEST_CALL_RE = re.compile(
    r"\.(?P<method>post|put|patch|delete)\s*\(\s*(?P<quote>['\"`])(?P<path>[^'\"`]+)(?P=quote)",
    re.IGNORECASE,
)
_TEST_CASE_RE = re.compile(
    r"\b(?:test|it)\s*\(\s*(?P<quote>['\"`])(?P<name>[^'\"`]+)(?P=quote)",
    re.IGNORECASE,
)
_TEST_HINT_RE = re.compile(r"\b(?:describe|it|test)\s*\(", re.IGNORECASE)


@dataclass
class ExpressSignals:
    has_express_import: bool
    has_write_routes: bool
    has_test_framework: bool


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _iter_files(repo_path: Path) -> list[Path]:
    files: list[Path] = []
    for root, dirs, filenames in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        root_path = Path(root)
        for filename in filenames:
            files.append(root_path / filename)
    return files


def _iter_js_files(all_files: list[Path]) -> list[Path]:
    return [path for path in all_files if path.suffix.lower() in JS_SUFFIXES]


def _is_test_file(path: Path) -> bool:
    lowered_name = path.name.lower()
    lowered_parts = {part.lower() for part in path.parts}
    return (
        lowered_name.endswith((".test.js", ".spec.js", ".test.ts", ".spec.ts", ".test.mjs", ".spec.mjs"))
        or lowered_name.startswith("test_")
        or "__tests__" in lowered_parts
        or "tests" in lowered_parts
        or "test" in lowered_parts
    )


def _line_from_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _line_snippet(source_lines: list[str], line: int, *, window: int = 3) -> str:
    start = max(0, line - 1)
    end = min(len(source_lines), start + window)
    return "\n".join(part.rstrip() for part in source_lines[start:end]).strip()


def _normalize_endpoint_name(method: str, route_path: str, line: int, handler: str | None) -> str:
    if handler and handler not in {"async", "function"}:
        return handler
    normalized_path = re.sub(r"[^a-zA-Z0-9]+", "_", route_path).strip("_").lower() or "root"
    return f"{method.lower()}_{normalized_path}_{line}"


def _extract_write_endpoints(path: Path, repo_path: Path, text: str, source_lines: list[str]) -> list[tuple[str, str, str, str, int, str]]:
    endpoints: list[tuple[str, str, str, str, int, str]] = []
    rel_path = str(path.relative_to(repo_path))

    for match in _ROUTE_CALL_RE.finditer(text):
        receiver = match.group("receiver").lower()
        if receiver not in {"app", "router"} and not receiver.endswith("router"):
            continue
        method = match.group("method").upper()
        route_path = match.group("path")
        line = _line_from_offset(text, match.start())
        handler = match.group("handler")
        endpoint_name = _normalize_endpoint_name(method, route_path, line, handler)
        endpoints.append(
            (
                rel_path,
                endpoint_name,
                method,
                route_path,
                line,
                _line_snippet(source_lines, line),
            )
        )
    return endpoints


def _nearest_test_name(source_lines: list[str], line: int) -> str:
    start = max(0, line - 20)
    for idx in range(line - 1, start - 1, -1):
        match = _TEST_CASE_RE.search(source_lines[idx])
        if match:
            return match.group("name").strip() or f"test_line_{line}"
    return f"test_line_{line}"


def _extract_test_cases(path: Path, repo_path: Path, source_lines: list[str]) -> list[tuple[str, str, int, str]]:
    rel_path = str(path.relative_to(repo_path))
    rows: list[tuple[str, str, int, str]] = []
    for idx, line in enumerate(source_lines, start=1):
        match = _TEST_CASE_RE.search(line)
        if not match:
            continue
        rows.append((rel_path, match.group("name").strip(), idx, _line_snippet(source_lines, idx)))
    return rows


def _extract_test_http_calls(path: Path, repo_path: Path, text: str, source_lines: list[str]) -> list[tuple[str, str, str, str, int, str]]:
    rel_path = str(path.relative_to(repo_path))
    rows: list[tuple[str, str, str, str, int, str]] = []
    for match in _TEST_CALL_RE.finditer(text):
        method = match.group("method").upper()
        route_path = match.group("path")
        line = _line_from_offset(text, match.start())
        test_name = _nearest_test_name(source_lines, line)
        rows.append((rel_path, test_name, method, route_path, line, _line_snippet(source_lines, line)))
    return rows


def scan_express_signals(repo_path: Path) -> ExpressSignals:
    all_files = _iter_files(repo_path)
    js_files = _iter_js_files(all_files)
    has_express_import = False
    has_write_routes = False
    has_test_framework = False

    for path in js_files:
        text = _read_text(path)
        if not text:
            continue
        if not has_express_import and _EXPRESS_IMPORT_RE.search(text):
            has_express_import = True
        if not has_write_routes and not _is_test_file(path):
            for match in _ROUTE_CALL_RE.finditer(text):
                receiver = match.group("receiver").lower()
                if receiver in {"app", "router"} or receiver.endswith("router"):
                    has_write_routes = True
                    break
        if not has_test_framework and _is_test_file(path) and _TEST_HINT_RE.search(text):
            has_test_framework = True

    return ExpressSignals(
        has_express_import=has_express_import,
        has_write_routes=has_write_routes,
        has_test_framework=has_test_framework,
    )


def collect_express_artifacts(repo_path: Path) -> ArtifactBundle:
    all_files = _iter_files(repo_path)
    js_files = _iter_js_files(all_files)
    test_files = [path for path in js_files if _is_test_file(path)]

    write_endpoints: list[tuple[str, str, str, str, int | None, str]] = []
    test_cases: list[tuple[str, str, int | None, str]] = []
    test_http_calls: list[tuple[str, str, str, str, int | None, str]] = []
    for path in js_files:
        text = _read_text(path)
        if not text:
            continue
        source_lines = text.splitlines()
        if _is_test_file(path):
            test_cases.extend(_extract_test_cases(path, repo_path, source_lines))
            test_http_calls.extend(_extract_test_http_calls(path, repo_path, text, source_lines))
            continue
        write_endpoints.extend(_extract_write_endpoints(path, repo_path, text, source_lines))

    return ArtifactBundle(
        all_files=all_files,
        write_endpoints=write_endpoints,
        test_files=test_files,
        test_cases=test_cases,
        test_http_calls=test_http_calls,
        dependency_specs=extract_dependency_specs(repo_path, all_files),
    )


__all__ = ["ExpressSignals", "collect_express_artifacts", "scan_express_signals"]
