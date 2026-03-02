# Capability Signal Map

This document defines the core stack-agnostic capability signals for AI Risk Manager.
The goal is to avoid `framework x scenario` explosion by mapping each backend plugin to a shared signal model.

## Status Legend

- `implemented`: extracted and used in deterministic rules.
- `partial`: extracted for some stacks or not yet enforced by deterministic rules.
- `missing`: not extracted as a first-class capability yet.

## Core 8 Signals

| Signal | Meaning | Current extraction source | Graph expression | Rule coverage | Status |
|---|---|---|---|---|---|
| `http_write_surface` | Mutating HTTP operations (`POST/PUT/PATCH/DELETE`) | `ArtifactBundle.write_endpoints` from `fastapi_artifacts.py` and `django_artifacts.py` | `Node(type=\"API\")` with `details.method/details.path` | `critical_path_no_tests` baseline scope | implemented |
| `request_contract_binding` | Request/response schema binding to write endpoints | `ArtifactBundle.endpoint_models` + `pydantic_models` (FastAPI path) | `Edge(type=\"validated_by\")` from API to Entity | indirect only (context for AI stage, no dedicated deterministic rule) | partial |
| `state_transition_declared` | Declared state machine transitions | `ArtifactBundle.declared_transitions` | `TransitionSpec` + `Node(type=\"Transition\")` + `Edge(type=\"transitions_to\")` | `missing_transition_handler` | implemented |
| `state_transition_handled_guarded` | Runtime status mutation and guard presence | `ArtifactBundle.handled_transitions` (`invariant_guarded`) | `Graph.handled_transitions` entries | `broken_invariant_on_transition` | implemented |
| `test_to_endpoint_coverage` | Evidence that tests exercise write paths | `ArtifactBundle.test_cases` + `test_http_calls` (path params, aliases, fixture/reverse mapping) | `Node(type=\"TestCase\")` + `Edge(type=\"covered_by\")` | `critical_path_no_tests` | implemented |
| `dependency_version_policy` | Supply-chain risk from mutable dependency specs | `ArtifactBundle.dependency_specs` via shared extractor (`pyproject.toml` + requirements files) | `Node(type=\"Dependency\")` with `details.policy_violation/scope` | `dependency_risk_policy_violation` | implemented |
| `side_effect_emit_contract` | Mandatory side-effect after critical write (event, notification, webhook, job) | Not first-class today | None yet | None yet | missing |
| `authorization_boundary_enforced` | Authz checks on critical path writes | Not first-class today (guard hints only cover transition invariants) | None yet | None yet (no dedicated auth rule) | missing |

## Rule-to-Signal Dependency

| Deterministic rule | Required signals |
|---|---|
| `critical_path_no_tests` | `http_write_surface`, `test_to_endpoint_coverage` |
| `missing_transition_handler` | `state_transition_declared`, `state_transition_handled_guarded` |
| `broken_invariant_on_transition` | `state_transition_handled_guarded`, `state_transition_declared` |
| `dependency_risk_policy_violation` | `dependency_version_policy` |

## Current Gaps Blocking Higher Coverage

1. No first-class side-effect contract (`db write -> required emit/notify`).
2. No deterministic authorization enforcement rule for write endpoints.
3. Contract binding is FastAPI-oriented (`pydantic_models`) and only partially generalized for Django/DRF.

## Recommended Next Capability Pack (Highest ROI)

1. Add `side_effect_emit_contract` extraction.
   - Collector artifacts: required emit operations + observed emit operations per write endpoint.
   - Rule: `missing_required_side_effect`.
   - Eval: one pass case, one fail case (missing emit).
2. Add `authorization_boundary_enforced` extraction.
   - Collector artifacts: endpoint auth decorators/permissions/policy checks.
   - Rule: `critical_write_missing_authz`.
   - Eval: endpoint with and without authz guard.
3. Generalize contract binding beyond Pydantic naming.
   - Normalize request/response model extraction for Django serializers.
   - Add deterministic rule hook once confidence is high.

## Plugin Contract for New Backends

To keep scaling linear, each new plugin should map backend syntax to these same capability signals, not add custom rule families first.

Minimum for `l1`:

- `http_write_surface`
- `test_to_endpoint_coverage`
- preflight signal quality checks

Minimum for `l2`:

- all `l1` capabilities
- `state_transition_declared` and `state_transition_handled_guarded` or explicit unsupported marker
- `dependency_version_policy`
- stable eval parity cases and passing trust/expansion gates
