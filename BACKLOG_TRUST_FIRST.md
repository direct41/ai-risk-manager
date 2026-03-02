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

## Delivery Sequence (Gate-Based)
1. Epic 1
2. Epic 2
3. Epic 3
4. Epic 4
5. Epic 5
6. Epic 6
