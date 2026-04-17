from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path

from ai_risk_manager.profiles.base import ProfileApplicability, ProfileId
from ai_risk_manager.profiles.ui_flow_smoke import load_ui_smoke_manifest, run_ui_smoke
from ai_risk_manager.signals.types import SignalBundle

_UI_CODE_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte"}
_UI_FILE_SUFFIXES = _UI_CODE_SUFFIXES | {".html", ".css"}
_PUBLIC_UI_DIRS = {"public", "static"}
_APP_SHELL_FILENAMES = {"index.html", "app.js", "main.js", "styles.css", "style.css"}
_EXPLICIT_ROUTE_MARKER_DIRS = {"pages", "routes", "route", "views", "screens"} | _PUBLIC_UI_DIRS
_ROUTE_MARKER_DIRS = {"app"} | _EXPLICIT_ROUTE_MARKER_DIRS
_COMPONENT_MARKER_DIRS = {"components", "component", "ui", "widgets"}
_UI_MARKER_DIRS = _ROUTE_MARKER_DIRS | _COMPONENT_MARKER_DIRS | {"frontend", "web", "client"}
_APP_ROUTE_FILENAMES = {"page", "layout", "loading", "error", "not-found"}
_IGNORE_TOKENS = {
    "src",
    "app",
    "apps",
    "pages",
    "page",
    "routes",
    "route",
    "views",
    "view",
    "screens",
    "screen",
    "components",
    "component",
    "ui",
    "widgets",
    "shared",
    "common",
    "lib",
    "index",
    "layout",
    "loading",
    "error",
    "modal",
    "dialog",
}
_FRAMEWORK_DEPENDENCIES = {
    "nextjs": {"next"},
    "react": {"react", "react-dom"},
    "vue": {"vue"},
    "nuxt": {"nuxt"},
    "svelte": {"svelte", "@sveltejs/kit"},
    "remix": {"@remix-run/react"},
}
_SENSITIVE_UI_TOKENS = {
    "auth": {"auth", "login", "logout", "password", "session", "token", "signup", "signin"},
    "payment": {"payment", "billing", "checkout", "invoice", "subscription", "refund"},
    "admin": {"admin", "backoffice", "moderation", "operator", "staff"},
}


@dataclass
class UiFlowPreparedProfile:
    profile_id: ProfileId
    applicability: ProfileApplicability
    framework: str | None = None


@dataclass
class UiFlowScopeAssessment:
    review_focus: list[str]
    notes: list[str]
    changed_journeys: list[str]
    smoke_signals: SignalBundle


def _iter_candidate_files(repo_path: Path) -> list[Path]:
    excluded = {".git", ".venv", "venv", "node_modules", ".riskmap", "dist", "build", "coverage"}
    files: list[Path] = []
    for root, dirs, filenames in os.walk(repo_path):
        dirs[:] = [name for name in dirs if name not in excluded]
        root_path = Path(root)
        for filename in filenames:
            files.append(root_path / filename)
    return files


def _read_json(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _package_dependencies(repo_path: Path) -> set[str]:
    package_json = repo_path / "package.json"
    payload = _read_json(package_json)
    if payload is None:
        return set()

    dependencies: set[str] = set()
    for field in ("dependencies", "devDependencies"):
        raw = payload.get(field)
        if not isinstance(raw, dict):
            continue
        dependencies.update(str(name).strip() for name in raw.keys() if str(name).strip())
    return dependencies


def _has_static_shell_surface(normalized_files: set[str]) -> bool:
    for root in _PUBLIC_UI_DIRS:
        prefix = f"{root}/"
        has_index = f"{prefix}index.html" in normalized_files
        has_shell_asset = any(
            path.startswith(prefix)
            and Path(path).name in _APP_SHELL_FILENAMES
            and Path(path).name != "index.html"
            for path in normalized_files
        )
        if has_index and has_shell_asset:
            return True
    return False


def _detect_framework(repo_path: Path, files: list[Path]) -> str | None:
    dependencies = _package_dependencies(repo_path)
    for framework, hints in _FRAMEWORK_DEPENDENCIES.items():
        if dependencies & hints:
            return framework

    normalized_files = {str(path.relative_to(repo_path)).replace("\\", "/").lower() for path in files}
    if any(path.startswith("app/") and path.endswith((".tsx", ".jsx", ".js", ".ts")) for path in normalized_files):
        return "nextjs"
    if any("/routes/" in path or path.startswith("routes/") for path in normalized_files):
        return "frontend"
    if any("/pages/" in path or path.startswith("pages/") for path in normalized_files):
        return "frontend"
    if any("/components/" in path or path.startswith("components/") for path in normalized_files):
        return "frontend"
    if _has_static_shell_surface(normalized_files):
        return "vanilla"
    return None


def _has_ui_surface(repo_path: Path, files: list[Path]) -> bool:
    if _detect_framework(repo_path, files) is not None:
        return True
    normalized_files = {str(path.relative_to(repo_path)).replace("\\", "/").lower() for path in files}
    for path in files:
        relative = str(path.relative_to(repo_path)).replace("\\", "/").lower()
        parts = set(relative.split("/"))
        if parts & _PUBLIC_UI_DIRS and not _has_static_shell_surface(normalized_files):
            continue
        if path.suffix.lower() in _UI_FILE_SUFFIXES and parts & _UI_MARKER_DIRS:
            return True
    return False


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip()


def _is_ui_file(path: str) -> bool:
    normalized = _normalize_path(path).lower()
    suffix = Path(normalized).suffix.lower()
    if suffix not in _UI_FILE_SUFFIXES:
        return False
    parts = set(Path(normalized).parts)
    if "node_modules" in parts or "dist" in parts or "build" in parts:
        return False
    if parts & _UI_MARKER_DIRS:
        return True
    return False


def _is_route_like(path: str) -> bool:
    normalized = _normalize_path(path).lower()
    parts = set(Path(normalized).parts)
    if parts & _EXPLICIT_ROUTE_MARKER_DIRS:
        return True
    if "app" not in parts or parts & _COMPONENT_MARKER_DIRS:
        return False
    return Path(normalized).stem in _APP_ROUTE_FILENAMES


def _is_component_like(path: str) -> bool:
    parts = set(Path(path.lower()).parts)
    return bool(parts & _COMPONENT_MARKER_DIRS) and not _is_route_like(path)


def _path_tokens(path: str) -> list[str]:
    tokens: list[str] = []
    for part in Path(path).parts:
        lowered = part.lower()
        if Path(lowered).suffix in _UI_FILE_SUFFIXES:
            lowered = Path(lowered).stem
        lowered = lowered.replace(".", "_").replace("-", "_")
        for chunk in lowered.split("_"):
            chunk = chunk.strip()
            if not chunk or chunk in _IGNORE_TOKENS:
                continue
            tokens.append(chunk)
    return tokens


def _derive_journey(path: str) -> str | None:
    normalized = _normalize_path(path).lower()
    parts = Path(normalized).parts
    if parts and parts[0] in _PUBLIC_UI_DIRS and Path(normalized).name in _APP_SHELL_FILENAMES:
        return "app_shell"
    tokens = _path_tokens(path)
    if not tokens:
        return None
    return "/".join(tokens[:2])


def _dedupe(items: list[str], *, limit: int) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        ordered.append(cleaned)
        seen.add(cleaned)
        if len(ordered) >= limit:
            break
    return ordered


def _format_targets(targets: list[str]) -> str:
    return ", ".join(f"`{target}`" for target in targets)


@dataclass
class _ChangedUiScope:
    changed_ui_files: list[str]
    route_journeys: list[str]
    component_targets: list[str]
    token_set: set[str]


def _collect_changed_scope(changed_files: set[str] | None) -> _ChangedUiScope:
    if not changed_files:
        return _ChangedUiScope(changed_ui_files=[], route_journeys=[], component_targets=[], token_set=set())

    changed_ui_files = sorted(path for path in changed_files if _is_ui_file(path))
    route_journeys = _dedupe(
        [journey for path in changed_ui_files if _is_route_like(path) if (journey := _derive_journey(path))],
        limit=4,
    )
    component_targets = _dedupe(
        [journey for path in changed_ui_files if _is_component_like(path) if (journey := _derive_journey(path))],
        limit=4,
    )
    token_set: set[str] = set()
    for path in changed_ui_files:
        token_set.update(_path_tokens(path))
    return _ChangedUiScope(
        changed_ui_files=changed_ui_files,
        route_journeys=route_journeys,
        component_targets=component_targets,
        token_set=token_set,
    )


class UiFlowProfile:
    profile_id: ProfileId = "ui_flow_risk"

    def prepare(self, repo_path: Path) -> UiFlowPreparedProfile:
        files = _iter_candidate_files(repo_path)
        framework = _detect_framework(repo_path, files)
        if framework is None and not _has_ui_surface(repo_path, files):
            return UiFlowPreparedProfile(profile_id=self.profile_id, applicability="not_applicable", framework=None)
        return UiFlowPreparedProfile(profile_id=self.profile_id, applicability="partial", framework=framework or "frontend")

    def assess_changed_scope(
        self,
        prepared: UiFlowPreparedProfile,
        repo_path: Path,
        changed_files: set[str] | None,
    ) -> UiFlowScopeAssessment:
        if prepared.applicability == "not_applicable" or not changed_files:
            return UiFlowScopeAssessment(review_focus=[], notes=[], changed_journeys=[], smoke_signals=SignalBundle())

        scope = _collect_changed_scope(changed_files)
        if not scope.changed_ui_files:
            return UiFlowScopeAssessment(review_focus=[], notes=[], changed_journeys=[], smoke_signals=SignalBundle())

        focus: list[str] = []
        notes: list[str] = []
        if prepared.framework is not None:
            notes.append(f"ui_flow_risk detected {prepared.framework} UI surface.")
        notes.append(f"ui_flow_risk mapped {len(scope.changed_ui_files)} changed UI file(s).")

        if scope.route_journeys:
            focus.append(f"Review changed UI journeys: {_format_targets(scope.route_journeys)}.")
        if scope.component_targets:
            focus.append(f"Review shared UI components affecting: {_format_targets(scope.component_targets)}.")

        for area, keywords in _SENSITIVE_UI_TOKENS.items():
            if not (scope.token_set & keywords):
                continue
            if area == "auth":
                focus.append("Review auth UI error states, session boundaries, and browser flows before merge.")
            elif area == "payment":
                focus.append("Review payment UI states, retry paths, and confirmation flows before merge.")
            elif area == "admin":
                focus.append("Review privileged admin UI actions and role-gated flows before merge.")

        manifest, manifest_notes = load_ui_smoke_manifest(repo_path)
        notes.extend(manifest_notes)
        smoke_signals = SignalBundle()
        if scope.route_journeys:
            smoke_result = run_ui_smoke(
                repo_path=repo_path,
                manifest=manifest,
                changed_journeys=scope.route_journeys,
                evidence_refs={journey: [path for path in scope.changed_ui_files if _derive_journey(path) == journey] for journey in scope.route_journeys},
            )
            notes.extend(smoke_result.notes)
            smoke_signals = smoke_result.signals

        return UiFlowScopeAssessment(
            review_focus=_dedupe(focus, limit=3),
            notes=notes,
            changed_journeys=list(scope.route_journeys),
            smoke_signals=smoke_signals,
        )

    def describe_changed_scope(
        self,
        prepared: UiFlowPreparedProfile,
        repo_path: Path,
        changed_files: set[str] | None,
    ) -> tuple[list[str], list[str]]:
        assessment = self.assess_changed_scope(prepared, repo_path, changed_files)
        return assessment.review_focus, assessment.notes


__all__ = ["UiFlowPreparedProfile", "UiFlowProfile", "UiFlowScopeAssessment"]
