from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import re

from ai_risk_manager.signals.types import CapabilitySignal, SignalBundle, SignalKind

_SOURCE_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".cjs",
    ".mjs",
    ".ts",
    ".tsx",
    ".go",
    ".java",
    ".rb",
    ".php",
    ".rs",
    ".cs",
    ".kt",
    ".swift",
}
_JS_SOURCE_SUFFIXES = {".js", ".jsx", ".cjs", ".mjs", ".ts", ".tsx"}
_DOC_SUFFIXES = {".md", ".rst", ".adoc", ".txt"}
_DEPENDENCY_FILENAMES = {
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "constraints.txt",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
    "pipfile",
    "pipfile.lock",
    "go.mod",
    "go.sum",
    "cargo.toml",
    "cargo.lock",
    "gemfile",
    "gemfile.lock",
    "composer.json",
    "composer.lock",
}
_CONTRACT_FILENAMES = {
    "openapi.yaml",
    "openapi.yml",
    "swagger.yaml",
    "swagger.yml",
    "asyncapi.yaml",
    "asyncapi.yml",
}
_CONTRACT_SUFFIXES = {".proto", ".graphql", ".graphqls", ".avsc"}
_RUNTIME_CONFIG_FILENAMES = {
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "procfile",
    "fly.toml",
    "render.yaml",
    "render.yml",
    "railway.json",
}
_RUNTIME_CONFIG_SUFFIXES = {".tf", ".tfvars"}
_LOW_SIGNAL_SOURCE_DIRS = {
    "scripts",
    "script",
    "tools",
    "tooling",
    "examples",
    "example",
    "benchmarks",
    "benchmark",
    "fixtures",
    "testdata",
    "vendor",
    "third_party",
    "generated",
    "gen",
    "mock",
    "mocks",
    "seed",
    "seeds",
}
_TEST_SUPPORT_FILENAMES = {
    "conftest.py",
    "jest.config.js",
    "jest.config.cjs",
    "jest.config.mjs",
    "jest.config.ts",
    "vitest.config.js",
    "vitest.config.ts",
    "playwright.config.js",
    "playwright.config.ts",
    "cypress.config.js",
    "cypress.config.ts",
}
_SENSITIVE_AREAS: dict[str, tuple[str, ...]] = {
    "auth": ("auth", "login", "logout", "password", "token", "oauth", "saml", "session", "permission", "role", "acl"),
    "payment": ("payment", "payments", "billing", "invoice", "checkout", "charge", "refund", "payout", "wallet", "ledger", "subscription"),
    "admin": ("admin", "backoffice", "moderation", "operator", "staff", "superuser"),
}
_DIFF_FILE_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$")
_DIFF_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,\d+)? @@")
_MAPPING_KEY_RE = re.compile(r"""['"](?P<key>[A-Za-z_][A-Za-z0-9_.-]{2,})['"]\s*:""")
_ADDED_4XX_BRANCH_RE = re.compile(
    r"raise\s+HTTPException[\s\S]*?status_code\s*=\s*(?:status\.HTTP_[A-Z_]*4\d\d|4\d\d)",
    re.IGNORECASE,
)
_ADDED_NEGATIVE_TEST_RE = re.compile(
    r"(?:status_code|status)\s*(?:==|in)\s*(?:\{[^}]*4\d\d|4\d\d)|"
    r"pytest\.raises|assertRaises|assert[\s\S]{0,80}(?:error|detail|forbidden|unauthorized|conflict)",
    re.IGNORECASE,
)
_QUERY_ARRAY_LIMIT_RE = re.compile(r"\barrayLimit\s*:\s*(?P<limit>Infinity|\d+)\b")
_INDEXED_QUERY_TEST_RE = re.compile(
    r"(?:\[\s*\d+\s*\]|%5B\s*\d+\s*%5D|"
    r"(?:query|search|url|path|param)[\s\S]{0,120}(?:\[\s*['\"]?\s*\+|%5B\s*['\"]?\s*\+))",
    re.IGNORECASE,
)
_DOC_SCAN_EXCLUDED_DIRS = {
    ".git",
    ".riskmap",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "vendor",
    "venv",
}
_GETTEXT_MODULES = {"django.utils.translation", "gettext"}
_GETTEXT_FUNCTIONS = {
    "gettext",
    "gettext_lazy",
    "ugettext",
    "ugettext_lazy",
}
_EQUIVALENT_JS_METHOD_ALIASES = (
    (".trimRight(", ".trimEnd("),
    (".trimLeft(", ".trimStart("),
)
_NODE_MINIMUM_RE = re.compile(r"(?:^|\s)>=\s*(?P<major>\d+)")


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip()


def _path_parts(path: str) -> tuple[str, ...]:
    return tuple(part.lower() for part in Path(path).parts)


def _is_test_file(path: str) -> bool:
    parts = _path_parts(path)
    name = Path(path).name.lower()
    return (
        name in _TEST_SUPPORT_FILENAMES
        or
        name.startswith("test_")
        or name.endswith(("_test.py", ".test.js", ".spec.js", ".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx"))
        or "__tests__" in parts
        or "tests" in parts
        or "test" in parts
    )


def _is_workflow_file(path: str) -> bool:
    parts = _path_parts(path)
    return ".github" in parts and "workflows" in parts and Path(path).suffix.lower() in {".yml", ".yaml"}


def _is_dependency_file(path: str) -> bool:
    return Path(path).name.lower() in _DEPENDENCY_FILENAMES


def _is_contract_file(path: str) -> bool:
    name = Path(path).name.lower()
    suffix = Path(path).suffix.lower()
    parts = _path_parts(path)
    if name in _CONTRACT_FILENAMES or suffix in _CONTRACT_SUFFIXES:
        return True
    if "graphql" in parts and "schema" in name:
        return True
    return False


def _is_migration_file(path: str) -> bool:
    normalized = _normalize_path(path).lower()
    parts = _path_parts(path)
    name = Path(path).name.lower()
    if name == "schema.prisma":
        return True
    if "migrations" in parts:
        return True
    if "alembic" in parts and "versions" in parts:
        return True
    if len(parts) >= 2 and parts[0] == "db" and parts[1] == "migrate":
        return True
    if normalized.startswith("db/migrate/"):
        return True
    return False


def _is_runtime_config_file(path: str) -> bool:
    normalized = _normalize_path(path).lower()
    name = Path(path).name.lower()
    suffix = Path(path).suffix.lower()
    parts = _path_parts(path)
    if name in _RUNTIME_CONFIG_FILENAMES or name.startswith("dockerfile"):
        return True
    if suffix in _RUNTIME_CONFIG_SUFFIXES:
        return True
    if "helm" in parts or "charts" in parts or "k8s" in parts or "kubernetes" in parts:
        return True
    if normalized.startswith(".devcontainer/"):
        return True
    return False


def _is_doc_file(path: str) -> bool:
    return Path(path).suffix.lower() in _DOC_SUFFIXES


def _is_source_file(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    if suffix not in _SOURCE_SUFFIXES:
        return False
    parts = _path_parts(path)
    if (
        _is_test_file(path)
        or _is_workflow_file(path)
        or _is_doc_file(path)
        or _is_dependency_file(path)
        or _is_contract_file(path)
        or _is_migration_file(path)
        or _is_runtime_config_file(path)
        or any(part in _LOW_SIGNAL_SOURCE_DIRS for part in parts)
    ):
        return False
    return True


def _example_refs(paths: list[str], *, limit: int = 5) -> list[str]:
    return [_normalize_path(path) for path in sorted(paths)[:limit]]


def _path_tokens(path: str) -> set[str]:
    parts = _path_parts(path)
    tokens: set[str] = set()
    for part in parts:
        for chunk in part.replace(".", "_").replace("-", "_").split("_"):
            chunk = chunk.strip().lower()
            if chunk:
                tokens.add(chunk)
    stem = Path(path).stem.lower()
    for chunk in stem.replace(".", "_").replace("-", "_").split("_"):
        chunk = chunk.strip()
        if chunk:
            tokens.add(chunk)
    return tokens


def _sensitive_area_matches(paths: list[str], area: str) -> list[str]:
    keywords = set(_SENSITIVE_AREAS[area])
    matches: list[str] = []
    for path in paths:
        if _path_tokens(path) & keywords:
            matches.append(path)
    return matches


def _diff_mapping_key_renames(diff_text: str) -> list[tuple[str, str, str]]:
    current_file = ""
    removed: set[str] = set()
    added: set[str] = set()
    renames: list[tuple[str, str, str]] = []

    def flush() -> None:
        if not current_file or not _is_source_file(current_file):
            return
        removed_only = removed - added
        added_only = added - removed
        if len(removed_only) != 1 or len(added_only) != 1:
            return
        old_key = next(iter(removed_only))
        new_key = next(iter(added_only))
        if old_key != new_key:
            renames.append((current_file, old_key, new_key))

    for line in diff_text.splitlines():
        match = _DIFF_FILE_RE.match(line)
        if match:
            flush()
            current_file = _normalize_path(match.group(2))
            removed = set()
            added = set()
            continue
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("-"):
            removed.update(match.group("key") for match in _MAPPING_KEY_RE.finditer(line[1:]))
        elif line.startswith("+"):
            added.update(match.group("key") for match in _MAPPING_KEY_RE.finditer(line[1:]))
    flush()
    return renames


def _diff_added_lines_by_file(diff_text: str) -> dict[str, str]:
    current_file = ""
    added_by_file: dict[str, list[str]] = {}
    for line in diff_text.splitlines():
        match = _DIFF_FILE_RE.match(line)
        if match:
            current_file = _normalize_path(match.group(2))
            added_by_file.setdefault(current_file, [])
            continue
        if current_file and line.startswith("+") and not line.startswith("+++"):
            added_by_file[current_file].append(line[1:])
    return {path: "\n".join(lines) for path, lines in added_by_file.items()}


def _diff_added_line_numbers_by_file(diff_text: str) -> dict[str, set[int]]:
    current_file = ""
    current_line: int | None = None
    added_by_file: dict[str, set[int]] = {}
    for line in diff_text.splitlines():
        match = _DIFF_FILE_RE.match(line)
        if match:
            current_file = _normalize_path(match.group(2))
            current_line = None
            added_by_file.setdefault(current_file, set())
            continue

        hunk = _DIFF_HUNK_RE.match(line)
        if hunk:
            current_line = int(hunk.group("start"))
            continue
        if not current_file or current_line is None:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added_by_file[current_file].add(current_line)
            current_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            continue
        elif not line.startswith("\\"):
            current_line += 1
    return added_by_file


def _diff_changed_lines_by_file(diff_text: str) -> dict[str, tuple[list[str], list[str]]]:
    current_file = ""
    changed_by_file: dict[str, tuple[list[str], list[str]]] = {}
    for line in diff_text.splitlines():
        match = _DIFF_FILE_RE.match(line)
        if match:
            current_file = _normalize_path(match.group(2))
            changed_by_file.setdefault(current_file, ([], []))
            continue
        if not current_file or line.startswith("---") or line.startswith("+++"):
            continue
        removed, added = changed_by_file[current_file]
        if line.startswith("-"):
            removed.append(line[1:])
        elif line.startswith("+"):
            added.append(line[1:])
    return changed_by_file


def _is_equivalent_js_method_alias_rewrite(removed: str, added: str) -> bool:
    rewritten = removed
    replacement_count = 0
    for legacy, standard in _EQUIVALENT_JS_METHOD_ALIASES:
        count = rewritten.count(legacy)
        if count:
            replacement_count += count
            rewritten = rewritten.replace(legacy, standard)
    return replacement_count > 0 and rewritten == added


def _node_runtime_supports_standard_trim_aliases(repo_path: Path | None) -> bool:
    if repo_path is None:
        return False
    try:
        payload = json.loads((repo_path / "package.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False

    engines = payload.get("engines")
    node_constraint = engines.get("node") if isinstance(engines, dict) else None
    if not isinstance(node_constraint, str):
        return False

    alternatives = [part.strip() for part in node_constraint.split("||") if part.strip()]
    if not alternatives:
        return False
    minimums = [_NODE_MINIMUM_RE.search(alternative) for alternative in alternatives]
    return all(match is not None and int(match.group("major")) >= 10 for match in minimums)


def _all_source_changes_are_equivalent_alias_rewrites(
    changed_sources: list[str],
    diff_text: str | None,
    repo_path: Path | None,
) -> bool:
    if (
        not diff_text
        or not _node_runtime_supports_standard_trim_aliases(repo_path)
        or any(Path(path).suffix.lower() not in _JS_SOURCE_SUFFIXES for path in changed_sources)
    ):
        return False

    changed_lines = _diff_changed_lines_by_file(diff_text)
    for source_path in changed_sources:
        removed, added = changed_lines.get(source_path, ([], []))
        if not removed or len(removed) != len(added):
            return False
        if not all(
            _is_equivalent_js_method_alias_rewrite(old_line, new_line)
            for old_line, new_line in zip(removed, added, strict=True)
        ):
            return False
    return bool(changed_sources)


def _gettext_aliases(tree: ast.AST) -> set[str]:
    aliases: set[str] = set()
    if not isinstance(tree, ast.Module):
        return aliases
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.module not in _GETTEXT_MODULES:
            continue
        for imported in node.names:
            if imported.name in _GETTEXT_FUNCTIONS:
                aliases.add(imported.asname or imported.name)
    return aliases


def _dynamic_gettext_lines(
    repo_path: Path,
    source_path: str,
    added_lines: set[int],
) -> list[int]:
    if Path(source_path).suffix.lower() != ".py" or not added_lines:
        return []

    try:
        source = (repo_path / source_path).read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []

    aliases = _gettext_aliases(tree)
    if not aliases:
        return []

    dynamic_lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in aliases or not node.args or node.lineno not in added_lines:
            continue
        message = node.args[0]
        if not (isinstance(message, ast.Constant) and isinstance(message.value, str)):
            dynamic_lines.add(node.lineno)
    return sorted(dynamic_lines)


def _documented_key_refs(repo_path: Path, key: str) -> list[str]:
    escaped = re.escape(key)
    pattern = re.compile(
        rf"(?:[`'\"]{escaped}[`'\"]|\{{\{{\s*{escaped}\s*\}}\}}|\b{escaped}\b\s+(?:key|field|variable))",
        re.IGNORECASE,
    )
    refs: list[str] = []
    for root, dirs, filenames in os.walk(repo_path):
        dirs[:] = [name for name in dirs if name not in _DOC_SCAN_EXCLUDED_DIRS]
        root_path = Path(root)
        for filename in filenames:
            path = root_path / filename
            if path.suffix.lower() not in _DOC_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if pattern.search(text):
                refs.append(_normalize_path(str(path.relative_to(repo_path))))
    return sorted(refs)


def build_pr_diff_signal_bundle(
    repo_path: Path,
    diff_text: str | None,
    changed_files: set[str] | None,
) -> SignalBundle:
    if not diff_text:
        return SignalBundle()

    changed = {_normalize_path(path) for path in changed_files or set()}
    changed_docs = {path for path in changed if _is_doc_file(path)}
    signals: list[CapabilitySignal] = []
    for source_path, old_key, new_key in _diff_mapping_key_renames(diff_text):
        doc_refs = [path for path in _documented_key_refs(repo_path, old_key) if path not in changed_docs]
        if not doc_refs:
            continue
        evidence_refs = [source_path, *doc_refs[:4]]
        signals.append(
            CapabilitySignal(
                id=f"sig:pr-risk:documented-key-rename:{source_path}:{old_key}:{new_key}",
                kind="pr_change_risk",
                source_ref=source_path,
                confidence="high",
                evidence_refs=evidence_refs,
                attributes={
                    "issue_type": "documented_mapping_key_renamed_without_docs",
                    "old_key": old_key,
                    "new_key": new_key,
                    "documentation_files": ", ".join(doc_refs[:4]),
                },
            )
        )

    added_by_file = _diff_added_lines_by_file(diff_text)
    added_test_text = "\n".join(
        text for path, text in added_by_file.items() if path in changed and _is_test_file(path)
    )
    has_added_negative_test = bool(_ADDED_NEGATIVE_TEST_RE.search(added_test_text))
    if not has_added_negative_test:
        for source_path, added_text in added_by_file.items():
            if source_path not in changed or not _is_source_file(source_path):
                continue
            if not _ADDED_4XX_BRANCH_RE.search(added_text):
                continue
            signals.append(
                CapabilitySignal(
                    id=f"sig:pr-risk:new-4xx-without-negative-test:{source_path}",
                    kind="pr_change_risk",
                    source_ref=source_path,
                    confidence="high",
                    evidence_refs=[source_path],
                    attributes={
                        "issue_type": "new_4xx_branch_without_negative_test_delta",
                        "changed_test_count": str(
                            sum(1 for path in changed if _is_test_file(path))
                        ),
                    },
                )
            )

    has_indexed_query_test = bool(_INDEXED_QUERY_TEST_RE.search(added_test_text))
    if not has_indexed_query_test:
        for source_path, added_text in added_by_file.items():
            if (
                source_path not in changed
                or not _is_source_file(source_path)
                or Path(source_path).suffix.lower() not in _JS_SOURCE_SUFFIXES
            ):
                continue
            limits = [match.group("limit") for match in _QUERY_ARRAY_LIMIT_RE.finditer(added_text)]
            if not limits:
                continue
            signals.append(
                CapabilitySignal(
                    id=f"sig:pr-risk:query-array-limit-without-indexed-test:{source_path}",
                    kind="pr_change_risk",
                    source_ref=source_path,
                    confidence="high",
                    evidence_refs=[
                        source_path,
                        *sorted(path for path in changed if _is_test_file(path))[:4],
                    ],
                    attributes={
                        "issue_type": "query_array_limit_without_indexed_compat_test",
                        "array_limit": limits[-1],
                        "changed_test_count": str(sum(1 for path in changed if _is_test_file(path))),
                    },
                )
            )

    added_line_numbers = _diff_added_line_numbers_by_file(diff_text)
    for source_path in sorted(changed):
        if not _is_source_file(source_path):
            continue
        dynamic_lines = _dynamic_gettext_lines(
            repo_path,
            source_path,
            added_line_numbers.get(source_path, set()),
        )
        if not dynamic_lines:
            continue
        signals.append(
            CapabilitySignal(
                id=f"sig:pr-risk:dynamic-gettext-message:{source_path}:{dynamic_lines[0]}",
                kind="pr_change_risk",
                source_ref=source_path,
                confidence="high",
                evidence_refs=[source_path],
                attributes={
                    "issue_type": "dynamic_gettext_message",
                    "dynamic_message_count": str(len(dynamic_lines)),
                    "line_numbers": ", ".join(str(line) for line in dynamic_lines[:5]),
                },
            )
        )
    return SignalBundle(signals=signals, supported_kinds={"pr_change_risk"} if signals else set())


def build_pr_change_signal_bundle(
    changed_files: set[str] | None,
    diff_text: str | None = None,
    repo_path: Path | None = None,
) -> SignalBundle:
    empty_supported_kinds: set[SignalKind] = set()
    if not changed_files:
        return SignalBundle(signals=[], supported_kinds=empty_supported_kinds)

    normalized = sorted({_normalize_path(path) for path in changed_files if _normalize_path(path)})
    changed_tests = [path for path in normalized if _is_test_file(path)]
    changed_sources = [path for path in normalized if _is_source_file(path)]
    changed_dependencies = [path for path in normalized if _is_dependency_file(path)]
    changed_contracts = [path for path in normalized if _is_contract_file(path)]
    changed_migrations = [path for path in normalized if _is_migration_file(path)]
    changed_runtime_configs = [path for path in normalized if _is_runtime_config_file(path)]
    changed_workflows = [path for path in normalized if _is_workflow_file(path)]
    sensitive_candidates = [
        path
        for path in normalized
        if not _is_test_file(path) and not _is_dependency_file(path) and not _is_doc_file(path) and not _is_workflow_file(path)
    ]
    sensitive_matches_by_area = {area: _sensitive_area_matches(sensitive_candidates, area) for area in _SENSITIVE_AREAS}
    sensitive_source_paths = {
        path
        for matches in sensitive_matches_by_area.values()
        for path in matches
        if path in changed_sources
    }

    signals: list[CapabilitySignal] = []
    supported_kinds: set[SignalKind] = {"pr_change_risk"}

    equivalent_alias_only = _all_source_changes_are_equivalent_alias_rewrites(
        changed_sources,
        diff_text,
        repo_path,
    )
    if (
        changed_sources
        and not changed_tests
        and not equivalent_alias_only
        and not set(changed_sources).issubset(sensitive_source_paths)
    ):
        evidence_refs = _example_refs(changed_sources)
        primary = evidence_refs[0]
        signals.append(
            CapabilitySignal(
                id=f"sig:pr-risk:code-without-tests:{primary}",
                kind="pr_change_risk",
                source_ref=primary,
                confidence="medium",
                evidence_refs=evidence_refs,
                attributes={
                    "issue_type": "code_change_without_test_delta",
                    "changed_source_count": str(len(changed_sources)),
                    "changed_test_count": "0",
                    "example_files": ", ".join(evidence_refs),
                },
            )
        )

    if changed_dependencies and not changed_tests:
        evidence_refs = _example_refs(changed_dependencies)
        primary = evidence_refs[0]
        signals.append(
            CapabilitySignal(
                id=f"sig:pr-risk:deps-without-tests:{primary}",
                kind="pr_change_risk",
                source_ref=primary,
                confidence="medium",
                evidence_refs=evidence_refs,
                attributes={
                    "issue_type": "dependency_change_without_test_delta",
                    "changed_dependency_count": str(len(changed_dependencies)),
                    "changed_test_count": "0",
                    "example_files": ", ".join(evidence_refs),
                },
            )
        )

    if changed_contracts and not changed_tests:
        evidence_refs = _example_refs(changed_contracts)
        primary = evidence_refs[0]
        signals.append(
            CapabilitySignal(
                id=f"sig:pr-risk:contract-without-tests:{primary}",
                kind="pr_change_risk",
                source_ref=primary,
                confidence="medium",
                evidence_refs=evidence_refs,
                attributes={
                    "issue_type": "contract_change_without_test_delta",
                    "changed_contract_count": str(len(changed_contracts)),
                    "changed_test_count": "0",
                    "example_files": ", ".join(evidence_refs),
                },
            )
        )

    if changed_migrations and not changed_tests:
        evidence_refs = _example_refs(changed_migrations)
        primary = evidence_refs[0]
        signals.append(
            CapabilitySignal(
                id=f"sig:pr-risk:migration-without-tests:{primary}",
                kind="pr_change_risk",
                source_ref=primary,
                confidence="high",
                evidence_refs=evidence_refs,
                attributes={
                    "issue_type": "migration_change_without_test_delta",
                    "changed_migration_count": str(len(changed_migrations)),
                    "changed_test_count": "0",
                    "example_files": ", ".join(evidence_refs),
                },
            )
        )

    if changed_runtime_configs:
        evidence_refs = _example_refs(changed_runtime_configs)
        primary = evidence_refs[0]
        signals.append(
            CapabilitySignal(
                id=f"sig:pr-risk:runtime-config-review:{primary}",
                kind="pr_change_risk",
                source_ref=primary,
                confidence="medium",
                evidence_refs=evidence_refs,
                attributes={
                    "issue_type": "runtime_config_change_requires_review",
                    "changed_runtime_config_count": str(len(changed_runtime_configs)),
                    "example_files": ", ".join(evidence_refs),
                },
            )
        )

    if changed_workflows:
        evidence_refs = _example_refs(changed_workflows)
        primary = evidence_refs[0]
        signals.append(
            CapabilitySignal(
                id=f"sig:pr-risk:workflow-review:{primary}",
                kind="pr_change_risk",
                source_ref=primary,
                confidence="high",
                evidence_refs=evidence_refs,
                attributes={
                    "issue_type": "workflow_change_requires_review",
                    "changed_workflow_count": str(len(changed_workflows)),
                    "example_files": ", ".join(evidence_refs),
                },
            )
        )

    for area in ("auth", "payment", "admin"):
        matches = sensitive_matches_by_area[area]
        if not matches:
            continue
        evidence_refs = _example_refs(matches)
        primary = evidence_refs[0]
        signals.append(
            CapabilitySignal(
                id=f"sig:pr-risk:sensitive-{area}:{primary}",
                kind="pr_change_risk",
                source_ref=primary,
                confidence="high",
                evidence_refs=evidence_refs,
                attributes={
                    "issue_type": f"{area}_sensitive_path_change_requires_review",
                    "changed_sensitive_count": str(len(matches)),
                    "changed_test_count": str(len(changed_tests)),
                    "example_files": ", ".join(evidence_refs),
                },
            )
        )

    return SignalBundle(
        signals=signals,
        supported_kinds=supported_kinds if signals else empty_supported_kinds,
    )


__all__ = ["build_pr_change_signal_bundle", "build_pr_diff_signal_bundle"]
