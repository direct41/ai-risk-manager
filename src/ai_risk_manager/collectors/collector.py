from __future__ import annotations

from pathlib import Path

from ai_risk_manager.collectors.plugins.base import ArtifactBundle
from ai_risk_manager.collectors.plugins.registry import get_default_plugin
from ai_risk_manager.schemas.types import PreflightResult

_DEFAULT_PLUGIN = get_default_plugin()


def preflight_check(repo_path: Path) -> PreflightResult:
    """Backward-compatible wrapper around the default collector plugin."""
    return _DEFAULT_PLUGIN.preflight(repo_path)


def collect_artifacts(repo_path: Path) -> ArtifactBundle:
    """Backward-compatible wrapper around the default collector plugin."""
    return _DEFAULT_PLUGIN.collect(repo_path)
