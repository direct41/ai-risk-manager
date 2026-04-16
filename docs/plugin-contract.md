# Plugin Contract v1

Deprecated as the primary architecture model.
This document describes the current stack-plugin compatibility surface for the shipped `code_risk` profile.
Use `docs/architecture.md` for the canonical product architecture.

This document defines the collector plugin contract used by AI Risk Manager for stack-specific analyzers.

## Purpose

- Keep core risk logic stack-agnostic.
- Require each stack plugin to declare capability support explicitly.
- Prevent silent plugin drift with shared conformance checks.

## Contract Version

- Current version: `1`
- Code source of truth: `ai_risk_manager.collectors.plugins.contract`
- Plugin field: `plugin_contract_version`

## Required Plugin Fields

Each collector plugin must provide:

- `stack_id`
- `plugin_contract_version`
- `target_support_level` (`l0|l1|l2`)
- `supported_signal_kinds` (`set[SignalKind]`)
- `unsupported_signal_kinds` (`set[SignalKind]`)

Signal kinds:

- `ingress_surface`
- `http_write_surface`
- `test_to_ingress_coverage`
- `request_contract_binding`
- `state_transition_declared`
- `state_transition_handled_guarded`
- `test_to_endpoint_coverage`
- `dependency_version_policy`
- `side_effect_emit_contract`
- `authorization_boundary_enforced`
- `write_contract_integrity`
- `session_lifecycle_consistency`
- `html_render_safety`
- `ui_ergonomics`

## Support-Level Capability Requirements

Required as `supported`:

- `l0`: none
- `l1`: `http_write_surface`, `test_to_endpoint_coverage`
- `l2`: `http_write_surface`, `test_to_endpoint_coverage`, `dependency_version_policy`

Additional `l2` declaration rule:

- `state_transition_declared` and `state_transition_handled_guarded` must be declared explicitly as a pair:
  - both `supported`, or
  - both `unsupported`

## Conformance Rules

A plugin fails conformance if:

- `plugin_contract_version` is not `1`
- any declared signal kind is unknown
- a signal kind is present in both `supported_signal_kinds` and `unsupported_signal_kinds`
- required supported capabilities for the declared support level are missing
- a required supported capability is marked `unsupported`
- `l2` transition pair is not declared consistently

## Artifacts and Gates

- Test gate:
  - `tests/test_plugin_contract.py`
- Eval artifact:
  - `eval/results/plugin_conformance.json`
- Eval summary section:
  - `Plugin Conformance`

## Extension Guidance

When adding a new stack plugin to the current `code_risk` profile:

1. Implement `CollectorPlugin` + capability-signal mixin.
2. Declare `supported_signal_kinds` and `unsupported_signal_kinds`.
3. Set `target_support_level` conservatively.
4. Pass plugin conformance tests before enabling stricter rollout behavior.

Scaffold helper:

```bash
python scripts/init_stack_plugin.py --stack-id flask_pytest
```
