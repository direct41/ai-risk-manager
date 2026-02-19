from __future__ import annotations

from pathlib import Path

from ai_risk_manager.collectors.plugins.base import ArtifactBundle
from ai_risk_manager.collectors.plugins.registry import get_default_plugin
from ai_risk_manager.schemas.types import PreflightResult


def preflight_check(repo_path: Path) -> PreflightResult:
    """Backward-compatible wrapper around the default collector plugin."""
    return get_default_plugin().preflight(repo_path)


def collect_artifacts(repo_path: Path) -> ArtifactBundle:
    """Backward-compatible wrapper around the default collector plugin."""
    return get_default_plugin().collect(repo_path)
