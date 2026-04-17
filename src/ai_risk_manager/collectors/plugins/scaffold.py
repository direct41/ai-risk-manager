from __future__ import annotations

from dataclasses import dataclass
import re
from typing import cast

from ai_risk_manager.collectors.plugins.contract import ALL_SIGNAL_KINDS, REQUIRED_SUPPORTED_BY_LEVEL
from ai_risk_manager.schemas.types import AppliedSupportLevel
from ai_risk_manager.signals.types import SignalKind

_STACK_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_CLASS_NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9]*CollectorPlugin$")


@dataclass(frozen=True)
class PluginScaffoldSpec:
    stack_id: str
    class_name: str
    target_support_level: AppliedSupportLevel = "l1"
    extra_supported: tuple[SignalKind, ...] = ()
    explicit_unsupported: tuple[SignalKind, ...] = ()


def default_class_name(stack_id: str) -> str:
    words = [part for part in stack_id.split("_") if part]
    stem = "".join(word.capitalize() for word in words) or "Stack"
    return f"{stem}CollectorPlugin"


def validate_stack_id(stack_id: str) -> None:
    if not _STACK_ID_RE.fullmatch(stack_id):
        raise ValueError("stack_id must match regex ^[a-z][a-z0-9_]*$.")


def validate_class_name(class_name: str) -> None:
    if not _CLASS_NAME_RE.fullmatch(class_name):
        raise ValueError("class_name must match regex ^[A-Z][A-Za-z0-9]*CollectorPlugin$.")


def _normalize_signal_tuple(values: tuple[SignalKind, ...], *, field_name: str) -> set[SignalKind]:
    normalized: set[SignalKind] = set()
    for raw in values:
        if raw not in ALL_SIGNAL_KINDS:
            raise ValueError(f"{field_name} contains unknown signal kind: {raw!r}.")
        normalized.add(cast(SignalKind, raw))
    return normalized


def resolve_capability_sets(spec: PluginScaffoldSpec) -> tuple[set[SignalKind], set[SignalKind]]:
    validate_stack_id(spec.stack_id)
    validate_class_name(spec.class_name)

    supported = set(REQUIRED_SUPPORTED_BY_LEVEL[spec.target_support_level])
    extra_supported = _normalize_signal_tuple(spec.extra_supported, field_name="extra_supported")
    explicit_unsupported = _normalize_signal_tuple(spec.explicit_unsupported, field_name="explicit_unsupported")
    supported.update(extra_supported)

    if spec.target_support_level == "l2":
        transition_pair = {"state_transition_declared", "state_transition_handled_guarded"}
        if transition_pair.isdisjoint(supported):
            explicit_unsupported.update(cast(set[SignalKind], transition_pair))

    unsupported = {kind for kind in ALL_SIGNAL_KINDS if kind not in supported}
    unsupported.update(explicit_unsupported)
    overlap = supported & unsupported
    if overlap:
        raise ValueError(f"supported and unsupported overlap: {sorted(overlap)}")
    return supported, unsupported


def render_plugin_scaffold(spec: PluginScaffoldSpec) -> str:
    supported, unsupported = resolve_capability_sets(spec)
    supported_lines = "\n".join(f'        "{kind}",' for kind in sorted(supported))
    unsupported_lines = "\n".join(f'        "{kind}",' for kind in sorted(unsupported))
    return (
        "from __future__ import annotations\n"
        "\n"
        "from pathlib import Path\n"
        f'from typing import Literal\n'
        "\n"
        "from ai_risk_manager.collectors.plugins.base import ArtifactBundle, StackProbeResult\n"
        "from ai_risk_manager.collectors.plugins.sdk import CapabilitySignalPluginMixin\n"
        "from ai_risk_manager.schemas.types import PreflightResult\n"
        "\n"
        "\n"
        f"class {spec.class_name}(CapabilitySignalPluginMixin):\n"
        f'    stack_id: Literal["{spec.stack_id}"] = "{spec.stack_id}"\n'
        f'    target_support_level = "{spec.target_support_level}"\n'
        "    supported_signal_kinds = {\n"
        f"{supported_lines}\n"
        "    }\n"
        "    unsupported_signal_kinds = {\n"
        f"{unsupported_lines}\n"
        "    }\n"
        "\n"
        "    def probe(self, repo_path: Path) -> StackProbeResult | None:\n"
        "        # Replace this stub with stack detection logic for the generated plugin.\n"
        "        return None\n"
        "\n"
        "    def preflight(self, repo_path: Path, probe_data: object | None = None) -> PreflightResult:\n"
        "        # Replace this stub with stack preflight checks for the generated plugin.\n"
        '        return PreflightResult(status="PASS", reasons=[])\n'
        "\n"
        "    def collect(self, repo_path: Path) -> ArtifactBundle:\n"
        "        # Replace this stub with artifact extraction logic for the generated plugin.\n"
        "        return ArtifactBundle()\n"
        "\n"
        "\n"
        f'__all__ = ["{spec.class_name}"]\n'
    )
