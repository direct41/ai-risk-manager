# Capability Signal Map

This document defines the core stack-agnostic capability signals for AI Risk Manager.
The goal is to avoid `framework x scenario` explosion by mapping each backend plugin to a shared signal model.

## Status Legend

- `implemented`: extracted and used in deterministic rules.
- `partial`: extracted for some stacks or not yet enforced by deterministic rules.
- `missing`: not extracted as a first-class capability yet.

## Core 14 Signals

| Signal | Meaning | Current extraction source | Graph expression | Rule coverage | Status |
|---|---|---|---|---|---|
| `ingress_surface` | Unified sink contract for mutating ingress points across families (`http`, `webhook`, `job`, `cli_task`, `event_consumer`) | Derived in `signals.adapters` from plugin artifacts; current extraction is HTTP/webhook global with Express-first `job`, `cli_task`, and `event_consumer` heuristics | None yet | foundation only | implemented |
| `http_write_surface` | Mutating HTTP operations (`POST/PUT/PATCH/DELETE`) | `ArtifactBundle.write_endpoints` from `fastapi_artifacts.py` and `django_artifacts.py` | `Node(type=\"API\")` with `details.method/details.path` | `critical_path_no_tests` baseline scope | implemented |
| `test_to_ingress_coverage` | Test evidence mapped to normalized ingress families | Derived in `signals.adapters` from `test_http_calls`, test-case fallback, and Express-first `runJob`/`runCli`/`emitEvent` heuristics | None yet | foundation only | implemented |
| `request_contract_binding` | Request/response schema binding to write endpoints | `ArtifactBundle.endpoint_models` + `pydantic_models` (FastAPI path) | `Edge(type=\"validated_by\")` from API to Entity | indirect only (context for AI stage, no dedicated deterministic rule) | partial |
| `state_transition_declared` | Declared state machine transitions | `ArtifactBundle.declared_transitions` | `TransitionSpec` + `Node(type=\"Transition\")` + `Edge(type=\"transitions_to\")` | `missing_transition_handler` | implemented |
| `state_transition_handled_guarded` | Runtime status mutation and guard presence | `ArtifactBundle.handled_transitions` (`invariant_guarded`) | `Graph.handled_transitions` entries | `broken_invariant_on_transition` | implemented |
| `test_to_endpoint_coverage` | Evidence that tests exercise write paths | `ArtifactBundle.test_cases` + `test_http_calls` (path params, aliases, fixture/reverse mapping) | `Node(type=\"TestCase\")` + `Edge(type=\"covered_by\")` | `critical_path_no_tests` | implemented |
| `dependency_version_policy` | Supply-chain risk from mutable dependency specs | `ArtifactBundle.dependency_specs` via shared extractor (`pyproject.toml` + requirements files) | `Node(type=\"Dependency\")` with `details.policy_violation/scope` | `dependency_risk_policy_violation` | implemented |
| `side_effect_emit_contract` | Mandatory side-effect after critical write (event, notification, webhook, job) | `ArtifactBundle.side_effect_requirements` + `side_effect_emits` | None yet | `missing_required_side_effect` | partial |
| `authorization_boundary_enforced` | Authz checks on critical path writes | `ArtifactBundle.authorization_boundaries` (Express middleware extraction implemented) | None yet | `critical_write_missing_authz` | partial |
| `write_contract_integrity` | Data-integrity and boundary-contract anomalies in write paths | `ArtifactBundle.write_contract_issues` (Express-first full pack; FastAPI/Django parity includes scope/conflict heuristics via shared Python extractor) | None yet | `input_normalization_char_split`, `response_field_contract_mismatch`, `db_insert_binding_mismatch`, `critical_write_scope_missing_entity_filter`, `stale_write_without_conflict_guard`, `reading_time_round_down_to_zero`, `priority_formula_precedence_risk`, `overdue_date_string_comparison` | partial |
| `session_lifecycle_consistency` | Consistency of token/session storage lifecycle across login/logout flows | `ArtifactBundle.session_lifecycle_issues` (Express localStorage extraction plus shared Python `request.session` parity for FastAPI/Django) | None yet | `session_token_key_mismatch` | implemented |
| `html_render_safety` | Unsafe HTML sink usage for untrusted content | `ArtifactBundle.html_render_issues` (Express-first extraction; FastAPI/Django currently declare explicit unsupported because the current rule contract is sink-specific) | None yet | `stored_xss_unsafe_innerhtml` | partial |
| `ui_ergonomics` | UI state/layout quality risks affecting interaction reliability | `ArtifactBundle.ui_ergonomics_issues` (Express-first extraction; Python backend plugins declare explicit unsupported) | None yet | `pagination_page_not_normalized`, `save_button_partial_form_enabled`, `mobile_layout_min_width_overflow` | partial |

## Rule-to-Signal Dependency

| Deterministic rule | Required signals |
|---|---|
| `critical_path_no_tests` | `http_write_surface`, `test_to_endpoint_coverage` |
| `missing_transition_handler` | `state_transition_declared`, `state_transition_handled_guarded` |
| `broken_invariant_on_transition` | `state_transition_handled_guarded`, `state_transition_declared` |
| `dependency_risk_policy_violation` | `dependency_version_policy` |
| `missing_required_side_effect` | `side_effect_emit_contract` |
| `critical_write_missing_authz` | `http_write_surface`, `authorization_boundary_enforced` |
| `input_normalization_char_split` | `write_contract_integrity` (`issue_type=char_split_normalization`) |
| `response_field_contract_mismatch` | `write_contract_integrity` (`issue_type=response_field_alias_mismatch`) |
| `db_insert_binding_mismatch` | `write_contract_integrity` (`issue_type=db_insert_binding_mismatch`) |
| `critical_write_scope_missing_entity_filter` | `write_contract_integrity` (`issue_type=write_scope_missing_entity_filter`) |
| `stale_write_without_conflict_guard` | `write_contract_integrity` (`issue_type=stale_write_without_conflict_guard`) |
| `reading_time_round_down_to_zero` | `write_contract_integrity` (`issue_type=reading_time_rounding_floor_missing`) |
| `priority_formula_precedence_risk` | `write_contract_integrity` (`issue_type=priority_ternary_constant_branch`) |
| `overdue_date_string_comparison` | `write_contract_integrity` (`issue_type=date_string_compare_with_iso`) |
| `session_token_key_mismatch` | `session_lifecycle_consistency` |
| `stored_xss_unsafe_innerhtml` | `html_render_safety` |
| `pagination_page_not_normalized` | `ui_ergonomics` (`issue_type=pagination_page_not_normalized_after_mutation`) |
| `save_button_partial_form_enabled` | `ui_ergonomics` (`issue_type=save_button_partial_form_enabled`) |
| `mobile_layout_min_width_overflow` | `ui_ergonomics` (`issue_type=mobile_layout_min_width_overflow`) |

## Current Gaps Blocking Higher Coverage

1. Side-effect contract extraction remains incomplete across supported stacks.
2. HTML/UI packs remain Express-first; Python backend plugins now declare these as explicit unsupported instead of leaving capability status implicit.
3. Contract binding is still FastAPI-oriented (`pydantic_models`) and only partially generalized for Django/DRF.
4. Ingress-family model now covers `http`, `webhook`, `job`, `cli_task`, and `event_consumer`, but non-HTTP extraction is still Express-first.

## Recommended Next Capability Pack (Highest ROI)

1. Stabilize capability-depth pack (`write_contract_integrity`, `session_lifecycle_consistency`, `html_render_safety`) for `express_node`.
   - Add parity eval repos for positive/negative paths and tune conservative defaults.
2. Expand side-effect and authz capability extraction parity across supported stacks.
3. Generalize request/response contract extraction beyond Pydantic naming.
4. Promote support-level only after trust-gate stability (precision/evidence/verification KPIs).

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
