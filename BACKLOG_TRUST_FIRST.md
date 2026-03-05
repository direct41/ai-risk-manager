# Trust-First Backlog

## Goal
Build and scale AI Risk Manager through high-trust signal quality first, then stack expansion.

## Execution Mode
- This backlog is executed by stage-gates, not fixed calendar dates.
- Epic transition gates:
  - implementation for the current epic is complete
  - `pytest` is green
  - trust/eval gates pass for changed behavior
  - docs/compatibility/changelog are updated when contracts change

## North-Star KPIs
- Precision@5 in PR summary: >= 75%
- Evidence completeness: >= 95%
- Verification pass rate: >= 95%
- Actioned findings rate: >= 40%
- Avg triage time proxy: <= 10 min
- PR fallback-to-full rate: <= 15%

## Epic 1: Trust Platform (P0)
- Status: Done (2026-02-27)
- Outcome: quality regressions are caught automatically before rollout

### Stories
1. [x] Eval trust gates with explicit thresholds and CI enforcement.
2. [x] Trust gate artifact contract (`summary.json`, `summary.md`, `trust_gate.json`).
3. [x] Weekly trend tracking from eval artifacts.

### Definition of Done
- Weekly eval workflow fails on threshold breach.
- Thresholds are versioned in-repo.
- Gate outputs are visible in CI artifacts.

## Epic 2: Rule Precision and Explainability (P0)
- Status: Done (2026-02-27)
- Outcome: findings are actionable and low-noise

### Stories
1. [x] Tighten transition invariant detection (reduce false positives).
2. [x] Expand dependency policy rules with context-aware severity.
3. [x] Add explanation templates with concrete next action and evidence ranking.

### Definition of Done
- No net precision regression in eval.
- Each finding includes evidence refs and recommendation.

## Epic 3: CI Rollout Control (P0)
- Status: Done (2026-02-27)
- Outcome: safe adoption path from advisory to blocking modes

### Stories
1. [x] Support-level x CI-mode compatibility matrix as executable checks.
2. [x] Guardrails for `block-new-critical` (high-confidence + verified evidence only).
3. [x] PR comment policy for only-new high-signal findings.

### Definition of Done
- Deterministic mode behavior is stable in fork PRs.
- Blocking mode triggers are reproducible and auditable.

## Epic 4: Coverage Mapping Quality (P1)
- Status: Done (completion-gate)
- Outcome: stronger linkage between tests and risky paths

### Stories
1. [x] Improve HTTP call/path matching (path params, aliases).
2. [x] Add fixture-aware test mapping heuristics.
3. [x] Extend eval repos for coverage edge cases.

### Definition of Done
- Coverage-related false positives drop in eval.

## Epic 5: Policy Engine Externalization (P1)
- Status: Done (completion-gate)
- Outcome: teams tune strictness without code forks

### Stories
1. [x] Rule policy config file (`.airiskpolicy`) with defaults.
2. [x] Per-rule severity and gating overrides.
3. [x] Validation and schema for policy contract.

### Definition of Done
- Config-driven policy behavior with tests and docs.

## Epic 6: Next Stack Expansion (P2)
- Status: Done (completion-gate)
- Outcome: controlled growth after trust stabilization

### Stories
1. [x] Select next stack (Django/DRF).
2. [x] Build collector plugin and parity eval cases.
3. [x] Add support-level defaults and conservative auto-downgrade on preflight warnings.
4. [x] Add stack expansion readiness gate artifact (`eval/results/expansion_gate.json`).

### Definition of Done
- Trust gate is `PASSED` in eval summary.
- Expansion readiness gate is `OPEN` with required consecutive trust-pass runs.
- Required stack-parity eval cases pass (`milestone7_django_viewset`, `milestone8_django_dependency`).

## Epic 7: Universal Plugin Contract (P1)
- Status: Done (completion-gate)
- Outcome: all backend plugins integrate through one versioned contract

### Stories
1. [x] Define `plugin_contract_version` and required capabilities per support level (`l0/l1/l2`).
2. [x] Add plugin self-declared capability matrix and explicit unsupported markers.
3. [x] Add shared conformance test suite and make it mandatory in CI for each plugin.
4. [x] Publish plugin conformance artifact in eval outputs.

### Definition of Done
- Contract spec is versioned and documented.
- Existing plugins (`fastapi_pytest`, `django_drf`) pass conformance tests without exceptions.
- CI blocks plugin changes that violate contract requirements.

## Epic 8: Universal Risk Capability Pack (P1)
- Status: Completed
- Outcome: missing high-value risk scenarios are covered by shared core logic

### Stories
1. [x] Add extraction contract for `side_effect_emit_contract`.
2. [x] Add deterministic rule `missing_required_side_effect` with evidence-driven output.
3. [x] Add extraction contract for `authorization_boundary_enforced`.
4. [x] Add deterministic rule `critical_write_missing_authz` with policy integration.
5. [x] Add eval cases for pass/fail paths across current supported stacks.

### Definition of Done
- Both new signals are represented in the common signal model.
- New rules are deterministic, test-backed, and policy-configurable.
- Trust/eval gates show no net precision regression after enabling rules.

## Epic 9: Contract-Driven Stack Expansion Program (P2)
- Status: Completed
- Outcome: adding stacks does not multiply core complexity

### Stories
1. [x] Select next candidate stacks based on contract fit and expected risk coverage gain.
2. [x] Add plugin scaffolding/template based on Epic 7 contract.
3. [x] Deliver parity eval suites for each added stack (positive, negative, edge cases).
4. [x] Define support-level promotion criteria (`l0 -> l1 -> l2`) per stack.

### Definition of Done
- Each new stack plugin passes conformance suite and parity eval.
- Expansion readiness gate confirms stable trust metrics for newly added stacks.
- Core rule engine remains stack-agnostic (no stack-specific rule forks in core).

## Epic 10: Service-Grade Hardening (P2)
- Status: Completed
- Outcome: API/runtime is safe for broader deployment scenarios

### Stories
1. [x] Add API authn/authz controls and secure defaults for non-local usage.
2. [x] Add request-level guardrails (rate limits, input size/timeouts).
3. [x] Add operational controls (audit trail, run correlation IDs, failure diagnostics).
4. [x] Add deployment hardening docs and minimal security checklist.

### Definition of Done
- Threat model for API deployment path is documented and validated.
- Security and reliability smoke checks run in CI.
- Deployment docs define baseline secure configuration and known limits.

## Epic 11: Capability Depth for Existing Stacks (P0)
- Status: Planned
- Outcome: materially reduce false-negative rate on high-impact backend and web-app risk classes without core rule forks

### Stories
1. [ ] P0 capability pack: data-integrity and boundary contracts.
   - Add shared signals/rules for:
     - write contract integrity (input/output field mismatches, suspicious normalization patterns)
     - write scope boundary (critical update/delete missing entity filter)
     - stale write conflict guard (client timestamp/version overwrite without compare-and-set control)
     - session lifecycle consistency (login/logout key mismatch for active tokens)
2. [ ] P1 capability pack: frontend security sinks.
   - Add shared signal/rule for unsafe HTML sink usage (stored-XSS class) with evidence references.
3. [ ] P2 capability pack (policy-default optional): low-impact UI ergonomics.
   - Add conservative heuristics for pagination/page-index drift and form-completeness gating issues.
4. [ ] Add parity eval suites for pass/fail paths (`express_node` first), then extend to other supported stacks where feasible.
5. [ ] Keep new rules policy-configurable and conservative by default to protect precision KPIs.

### Definition of Done
- New capabilities are represented in stack-agnostic signal model and deterministic rules.
- No stack-specific rule forks are added in core.
- Trust/eval gates show no net precision regression; evidence completeness stays >= 95%.
- At least one parity pass/fail case per new capability is present in eval repos.

## Delivery Sequence (Gate-Based)
1. Epic 1
2. Epic 2
3. Epic 3
4. Epic 4
5. Epic 5
6. Epic 6
7. Epic 7
8. Epic 8
9. Epic 9
10. Epic 10
11. Epic 11
