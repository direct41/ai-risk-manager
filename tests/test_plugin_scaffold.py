from __future__ import annotations

import pytest

from ai_risk_manager.collectors.plugins.scaffold import (
    PluginScaffoldSpec,
    default_class_name,
    render_plugin_scaffold,
    resolve_capability_sets,
    validate_class_name,
    validate_stack_id,
)


def test_default_class_name_from_stack_id() -> None:
    assert default_class_name("flask_pytest") == "FlaskPytestCollectorPlugin"


def test_validation_rejects_invalid_identifiers() -> None:
    with pytest.raises(ValueError):
        validate_stack_id("Flask")
    with pytest.raises(ValueError):
        validate_class_name("flask_plugin")


def test_l1_scaffold_contains_required_capabilities() -> None:
    spec = PluginScaffoldSpec(stack_id="flask_pytest", class_name="FlaskPytestCollectorPlugin", target_support_level="l1")
    supported, unsupported = resolve_capability_sets(spec)

    assert "http_write_surface" in supported
    assert "test_to_endpoint_coverage" in supported
    assert "dependency_version_policy" in unsupported


def test_l2_scaffold_declares_transition_pair_when_not_supported() -> None:
    spec = PluginScaffoldSpec(stack_id="flask_pytest", class_name="FlaskPytestCollectorPlugin", target_support_level="l2")
    _, unsupported = resolve_capability_sets(spec)

    assert "state_transition_declared" in unsupported
    assert "state_transition_handled_guarded" in unsupported


def test_render_plugin_scaffold_outputs_expected_class_signature() -> None:
    spec = PluginScaffoldSpec(stack_id="flask_pytest", class_name="FlaskPytestCollectorPlugin", target_support_level="l1")
    rendered = render_plugin_scaffold(spec)

    assert "class FlaskPytestCollectorPlugin(CapabilitySignalPluginMixin):" in rendered
    assert 'stack_id: Literal["flask_pytest"] = "flask_pytest"' in rendered
    assert 'target_support_level = "l1"' in rendered
    assert "def collect(self, repo_path: Path) -> ArtifactBundle:" in rendered

