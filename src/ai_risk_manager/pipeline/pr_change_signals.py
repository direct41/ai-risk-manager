from __future__ import annotations

from pathlib import Path

from ai_risk_manager.signals.types import CapabilitySignal, SignalBundle

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


def build_pr_change_signal_bundle(changed_files: set[str] | None) -> SignalBundle:
    if not changed_files:
        return SignalBundle(signals=[], supported_kinds=set())

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
    supported_kinds = {"pr_change_risk"}

    if changed_sources and not changed_tests and not set(changed_sources).issubset(sensitive_source_paths):
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

    return SignalBundle(signals=signals, supported_kinds=supported_kinds if signals else set())


__all__ = ["build_pr_change_signal_bundle"]
