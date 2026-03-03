from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast, get_args

from ai_risk_manager.collectors.plugins.base import CollectorPlugin, StackId
from ai_risk_manager.schemas.types import AppliedSupportLevel
from ai_risk_manager.signals.types import SignalKind

PluginContractVersion = Literal["1"]
CapabilityStatus = Literal["supported", "unsupported", "unknown"]

PLUGIN_CONTRACT_VERSION: PluginContractVersion = "1"
ALL_SIGNAL_KINDS: tuple[SignalKind, ...] = cast(tuple[SignalKind, ...], get_args(SignalKind))

L1_REQUIRED_SUPPORTED: set[SignalKind] = {
    "http_write_surface",
    "test_to_endpoint_coverage",
}
L2_REQUIRED_SUPPORTED: set[SignalKind] = {
    "http_write_surface",
    "test_to_endpoint_coverage",
    "dependency_version_policy",
}
L2_TRANSITION_PAIR: set[SignalKind] = {
    "state_transition_declared",
    "state_transition_handled_guarded",
}

REQUIRED_SUPPORTED_BY_LEVEL: dict[AppliedSupportLevel, set[SignalKind]] = {
    "l0": set(),
    "l1": L1_REQUIRED_SUPPORTED,
    "l2": L2_REQUIRED_SUPPORTED,
}

SUPPORTED_LEVELS: tuple[AppliedSupportLevel, ...] = ("l0", "l1", "l2")


@dataclass(frozen=True)
class PluginConformanceReport:
    stack_id: StackId
    plugin_contract_version: str
    target_support_level: AppliedSupportLevel
    capability_matrix: dict[SignalKind, CapabilityStatus]
    passed: bool
    errors: list[str]


def _normalize_signal_set(attr_name: str, value: Any, errors: list[str]) -> set[SignalKind]:
    if not isinstance(value, set):
        errors.append(f"{attr_name} must be a set.")
        return set()
    normalized: set[SignalKind] = set()
    for item in value:
        if item not in ALL_SIGNAL_KINDS:
            errors.append(f"{attr_name} contains unknown signal kind: {item!r}.")
            continue
        normalized.add(cast(SignalKind, item))
    return normalized


def _capability_matrix(
    *,
    supported: set[SignalKind],
    unsupported: set[SignalKind],
) -> dict[SignalKind, CapabilityStatus]:
    matrix: dict[SignalKind, CapabilityStatus] = {}
    for kind in ALL_SIGNAL_KINDS:
        if kind in supported:
            matrix[kind] = "supported"
        elif kind in unsupported:
            matrix[kind] = "unsupported"
        else:
            matrix[kind] = "unknown"
    return matrix


def evaluate_plugin_conformance(plugin: CollectorPlugin) -> PluginConformanceReport:
    errors: list[str] = []
    stack_id = plugin.stack_id

    raw_version = getattr(plugin, "plugin_contract_version", "")
    plugin_contract_version = str(raw_version)
    if plugin_contract_version != PLUGIN_CONTRACT_VERSION:
        errors.append(
            "plugin_contract_version mismatch: "
            f"got '{plugin_contract_version}', expected '{PLUGIN_CONTRACT_VERSION}'."
        )

    raw_support_level = getattr(plugin, "target_support_level", "l0")
    if raw_support_level not in SUPPORTED_LEVELS:
        errors.append(f"target_support_level must be one of {SUPPORTED_LEVELS}, got: {raw_support_level!r}.")
        target_support_level: AppliedSupportLevel = "l0"
    else:
        target_support_level = cast(AppliedSupportLevel, raw_support_level)

    supported = _normalize_signal_set("supported_signal_kinds", getattr(plugin, "supported_signal_kinds", set()), errors)
    unsupported = _normalize_signal_set(
        "unsupported_signal_kinds",
        getattr(plugin, "unsupported_signal_kinds", set()),
        errors,
    )

    overlap = sorted(supported & unsupported)
    if overlap:
        errors.append(
            "Signal kinds cannot be both supported and unsupported: "
            f"{overlap}."
        )

    required_supported = REQUIRED_SUPPORTED_BY_LEVEL[target_support_level]
    missing_required_supported = sorted(required_supported - supported)
    if missing_required_supported:
        errors.append(
            f"Missing required supported capabilities for {target_support_level}: {missing_required_supported}."
        )

    marked_unsupported_but_required = sorted(required_supported & unsupported)
    if marked_unsupported_but_required:
        errors.append(
            "Capabilities required as supported cannot be marked unsupported: "
            f"{marked_unsupported_but_required}."
        )

    if target_support_level == "l2":
        transition_supported = L2_TRANSITION_PAIR.issubset(supported)
        transition_unsupported = L2_TRANSITION_PAIR.issubset(unsupported)
        if not (transition_supported or transition_unsupported):
            declared = supported | unsupported
            missing_transition = sorted(L2_TRANSITION_PAIR - declared)
            if missing_transition:
                errors.append(
                    "Transition capability pair must be explicitly declared for l2 "
                    f"(supported or unsupported): missing {missing_transition}."
                )
            else:
                errors.append(
                    "Transition capability pair must be declared with a single status for l2 "
                    "(both supported or both unsupported)."
                )

    capability_matrix = _capability_matrix(supported=supported, unsupported=unsupported)
    return PluginConformanceReport(
        stack_id=stack_id,
        plugin_contract_version=plugin_contract_version,
        target_support_level=target_support_level,
        capability_matrix=capability_matrix,
        passed=not errors,
        errors=errors,
    )

