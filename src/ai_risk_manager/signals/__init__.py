from __future__ import annotations

from ai_risk_manager.signals.types import CapabilitySignal, SignalBundle

__all__ = ["CapabilitySignal", "SignalBundle", "artifact_bundle_to_signal_bundle", "merge_signal_bundles"]


def artifact_bundle_to_signal_bundle(*args, **kwargs):
    # Lazy import avoids circular imports with collector plugin registration.
    from ai_risk_manager.signals.adapters import artifact_bundle_to_signal_bundle as _impl

    return _impl(*args, **kwargs)


def merge_signal_bundles(*args, **kwargs):
    from ai_risk_manager.signals.merge import merge_signal_bundles as _impl

    return _impl(*args, **kwargs)
