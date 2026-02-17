from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

from ai_risk_manager.schemas.types import PreflightResult

WRITE_METHODS = ("post", "put", "patch", "delete")


@dataclass
class ArtifactBundle:
    all_files: list[Path] = field(default_factory=list)
    python_files: list[Path] = field(default_factory=list)
    write_endpoints: list[tuple[str, str]] = field(default_factory=list)  # (file, endpoint_name)
    test_files: list[Path] = field(default_factory=list)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def preflight_check(repo_path: Path) -> PreflightResult:
    py_files = list(repo_path.rglob("*.py"))
    has_fastapi_import = False
    has_router = False
    has_pytest = False

    for path in py_files:
        text = _read_text(path)
        if not has_fastapi_import and re.search(r"\bfrom\s+fastapi\b|\bimport\s+fastapi\b", text):
            has_fastapi_import = True
        if not has_router and re.search(r"@\w*router\.(get|post|put|patch|delete)\(", text):
            has_router = True
        if not has_pytest and ("import pytest" in text or "from pytest" in text):
            has_pytest = True

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
    bundle.all_files = [p for p in repo_path.rglob("*") if p.is_file()]
    bundle.python_files = [p for p in bundle.all_files if p.suffix == ".py"]
    bundle.test_files = [p for p in bundle.python_files if "test" in p.name.lower() or "/tests/" in str(p)]

    endpoint_regex = re.compile(r"@(\w*router)\.(post|put|patch|delete|get)\([^\n]*\)\s*\ndef\s+(\w+)\(", re.MULTILINE)

    for path in bundle.python_files:
        text = _read_text(path)
        for match in endpoint_regex.finditer(text):
            method = match.group(2)
            func_name = match.group(3)
            if method in WRITE_METHODS:
                bundle.write_endpoints.append((str(path), func_name))

    return bundle
