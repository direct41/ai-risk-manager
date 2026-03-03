from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from ai_risk_manager.collectors.plugins.contract import PLUGIN_CONTRACT_VERSION
from ai_risk_manager.collectors.plugins.base import ArtifactBundle
from ai_risk_manager.schemas.types import AppliedSupportLevel
from ai_risk_manager.signals.adapters import artifact_bundle_to_signal_bundle
from ai_risk_manager.signals.types import SignalBundle, SignalKind


@runtime_checkable
class CapabilitySignalPlugin(Protocol):
    supported_signal_kinds: set[SignalKind]

    def collect_signals(self, repo_path: Path) -> SignalBundle:
        ...

    def collect_signals_from_artifacts(self, artifacts: ArtifactBundle) -> SignalBundle:
        ...


class CapabilitySignalPluginMixin:
    plugin_contract_version = PLUGIN_CONTRACT_VERSION
    target_support_level: AppliedSupportLevel = "l2"
    supported_signal_kinds: set[SignalKind] = set()
    unsupported_signal_kinds: set[SignalKind] = set()

    def collect_signals(self, repo_path: Path) -> SignalBundle:
        collect_fn = getattr(self, "collect", None)
        if collect_fn is None:
            raise TypeError("CapabilitySignalPluginMixin requires a collect(repo_path) method")
        artifacts = collect_fn(repo_path)
        return self.collect_signals_from_artifacts(artifacts)

    def collect_signals_from_artifacts(self, artifacts: ArtifactBundle) -> SignalBundle:
        bundle = artifact_bundle_to_signal_bundle(artifacts)
        bundle.supported_kinds.update(self.supported_signal_kinds)
        return bundle
