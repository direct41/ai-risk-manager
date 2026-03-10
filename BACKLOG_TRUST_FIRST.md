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
- Status: Completed
- Outcome: materially reduce false-negative rate on high-impact backend and web-app risk classes without core rule forks

### Stories
1. [x] P0 capability pack: data-integrity and boundary contracts.
   - Add shared signals/rules for:
     - write contract integrity (input/output field mismatches, suspicious normalization patterns)
     - write scope boundary (critical update/delete missing entity filter)
     - stale write conflict guard (client timestamp/version overwrite without compare-and-set control)
     - session lifecycle consistency (login/logout key mismatch for active tokens)
2. [x] P1 capability pack: frontend security sinks.
   - Add shared signal/rule for unsafe HTML sink usage (stored-XSS class) with evidence references.
3. [x] P2 capability pack (policy-default optional): low-impact UI ergonomics.
   - Add conservative heuristics for pagination/page-index drift and form-completeness gating issues.
4. [x] Add parity eval suites for pass/fail paths (`express_node` first), then extend to other supported stacks where feasible.
5. [x] Keep new rules policy-configurable and conservative by default to protect precision KPIs.

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

## Epic 12: Capability-Pack Promotion Stabilization (P1)
- Status: Completed
- Outcome: new capability packs are promoted through explicit eval evidence instead of implicit stack-level readiness

### Stories
1. [x] Add capability-pack promotion policy separate from stack promotion.
2. [x] Publish eval artifact for pack-level promotion readiness.
3. [x] Gate pack readiness on parity cases plus consecutive trust-pass history.
4. [x] Surface pack readiness in eval summary for review and rollout decisions.

### Definition of Done
- Eval produces a dedicated `capability_pack_promotion.json` artifact.
- Each promoted pack has explicit required cases and trust-pass thresholds.
- Summary output shows which capability packs are eligible or blocked and why.

## Epic 13: Ingress Contract Generalization (P0)
- Status: Completed
- Outcome: the core analyzer stops being implicitly HTTP-centric and can reason about multiple sink families through one contract model

### Stories
1. [x] Define versioned ingress contracts for `http`, `webhook`, `job`, `event_consumer`, and `cli/task` surfaces.
2. [x] Extend the common signal model so capability packs can attach to ingress families, not only current HTTP shapes.
3. [x] Add parity eval cases for at least one non-HTTP sink family.
4. [x] Keep existing runtime behavior backward-compatible for current stacks.

### Definition of Done
- New ingress contracts are versioned in-repo and mapped to current plugin boundaries.
- Core rules remain stack-agnostic and do not add framework-specific branches.
- Eval shows that non-HTTP sink support works without regressing trust metrics on existing HTTP scenarios.

## Epic 14: Capability Parity Across Supported Stacks (P0)
- Status: Planned
- Outcome: Stage 11 capability packs stop being `express_node`-first and become portable across the current supported stack set

### Stories
1. [ ] Add `write_contract_integrity` parity extraction for `fastapi_pytest`.
2. [ ] Add `write_contract_integrity` parity extraction for `django_drf`.
3. [ ] Add `session_lifecycle_consistency` and `html_render_safety` parity where stack semantics allow it.
4. [ ] Promote each capability pack independently through existing pack-promotion gates.

### Definition of Done
- Each Stage 11 capability pack is implemented for at least two supported stacks.
- Promotion status is visible per pack, not inferred from a stack-level label.
- Trust/eval gates remain green after parity rollout.

## Epic 15: Advisory AI Extraction For Partial Support (P1)
- Status: Planned
- Outcome: the product can analyze partially supported repositories without pretending they have deterministic parity

### Stories
1. [ ] Define evidence-bound AI extraction contract for generic repository analysis.
2. [ ] Introduce advisory-only support level behavior for AI-assisted partial coverage.
3. [ ] Add deterministic verification anchors and explicit drop rules for unverifiable AI claims.
4. [ ] Add eval scenarios for "supported", "partial", and "unsupported but advisory" repository states.

### Definition of Done
- AI-assisted findings without evidence are dropped automatically.
- Partially supported repositories receive explicit support-level labeling and conservative rollout behavior.
- Eval artifacts show trust metrics separately for deterministic and AI-assisted paths.

## Epic 16: External Plugin Distribution Model (P2)
- Status: Planned
- Outcome: new stack analyzers can be developed and distributed without modifying core runtime boundaries

### Stories
1. [ ] Define the packaging and loading contract for external plugins.
2. [ ] Publish a stable plugin SDK/template based on the existing contract model.
3. [ ] Add trust and conformance gates for externally supplied plugins.
4. [ ] Document repository and release guidance for plugin authors.

### Definition of Done
- External plugin loading is possible without weakening core trust gates.
- Plugin authors have a stable scaffold and conformance workflow.
- Core runtime does not become responsible for plugin-specific business logic.
