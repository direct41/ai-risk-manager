# Profile-Based, Capability-Aware Architecture

## Decision

AI Risk Manager evolves as a single merge-risk pipeline with optional `risk profiles`.

The product does **not** expand by adding more stack-specific top-level architectures.
It expands by attaching new profiles to the same pipeline:

- `code_risk`
- `ui_flow_risk`
- `business_invariant_risk`

Each profile declares whether it is:

- `supported`
- `partial`
- `not_applicable`

This replaces the older idea that the whole product should be described primarily by stack plugins or stack expansion waves.

## Why This Decision

Different repositories have different risk surfaces:

- backend/API only
- backend + web UI
- workers / jobs / workflows
- repositories with explicit domain invariants

Forcing one global stack-centric model creates two bad outcomes:

- false expectations on repositories where a surface does not exist
- architecture sprawl as every new surface becomes another stack-specific branch

The profile model avoids both.

## Design Goals

- Keep one pipeline and one delivery contract.
- Run only checks that are relevant to the repository.
- Make `not_applicable` a first-class outcome.
- Keep findings evidence-backed and deterministic-first.
- Let new capability packs plug into the same summary, scoring, and PR workflow.

## Canonical Flow

1. Repository discovery collects technology hints and changed scope.
2. Profile selector activates only relevant risk profiles.
3. Each active profile collects facts and adapts them into `CapabilitySignal`s.
4. Shared rules evaluate signals into findings.
5. Shared scoring and triage rank findings for merge review.
6. Shared report generation emits `report.md`, `merge_triage.md`, `pr_summary.md`, `pr_summary.json`, and `github_check.json`.

Current runtime note:

- shipped PR-facing summaries already expose active profile applicability and compact trust metadata for top findings

One pipeline. Multiple profiles. One output contract.

## Core Runtime

The current code already has the right core modules:

- `collectors`
- `signals`
- `rules`
- `triage`
- `reports`
- `pipeline`

Those remain the center of the system.

The new architectural work is to add a thin profile registry above them, not to replace them.

## Risk Profiles

### `code_risk`

Purpose:

- backend/API risk
- workflow automation risk
- generated test quality
- universal PR delta heuristics

Current state:

- shipped today
- strongest support on `fastapi_pytest`, `django_drf`, `express_node`
- partial value on unknown stacks through universal heuristics

### `ui_flow_risk`

Purpose:

- visual regressions
- UX breakage on changed journeys
- browser-specific smoke coverage
- critical user-flow instability

Rules:

- only runs if a UI surface is detected
- recognizes both routed frontend layouts and simple `public/` or `static/` app shells
- operates on changed routes/pages/components, not whole-site blanket scans
- emits targeted review focus and evidence, not generic screenshot noise
- may run declared repo-owned smoke commands for changed journeys only

Current state:

- shipped as discovery-first MVP
- browser execution is opt-in through `./.riskmap-ui.toml` and limited to declared changed journeys
- command execution also requires `AIRISK_UI_SMOKE_ENABLE_COMMANDS=1`, and should only be used for trusted repositories
- screenshot diffing and browser matrices are intentionally not shipped

### `business_invariant_risk`

Purpose:

- business-rule conformance around critical flows
- explicit state and policy invariants
- domain-sensitive negative-path expectations

Rules:

- requires repository-owned invariant specification
- does not guess business logic from code alone
- treats missing specification as `not_applicable`, not as failure

Current state:

- scaffold and first rule shipped
- profile is `not_applicable` unless `.riskmap.yml` or `.riskmap.yaml` exists
- first PR-scoped rule pack shipped for `critical_flows`
- emits one deterministic finding when a declared critical flow changes without a matching check delta
- state/auth/payment/admin invariant enforcement is still pending

## Applicability Matrix

The product should describe support per profile, not only per repository.

Example:

| Repository type | `code_risk` | `ui_flow_risk` | `business_invariant_risk` |
|---|---|---|---|
| API-only service | supported | not_applicable | partial or not_applicable |
| SaaS web app | supported | partial/supported | partial |
| Worker/ETL repo | partial | not_applicable | not_applicable |

This is the correct abstraction for heterogeneous products.

## Trust Layer

Every finding should be evaluated through the same trust model:

- evidence strength
- support/applicability level
- historical rule precision
- repository suppression history

This should be implemented as a shared scoring layer, not separately inside each profile.

## Compatibility Shims

The current runtime still contains stack-centric compatibility surfaces:

- `stacks.discovery`
- stack plugin registry
- plugin contract v1
- repository-wide `support_level_applied`
- repository-wide `repository_support_state`
- reporting-era metadata such as `competitive_mode` and `graph_mode_applied`

These stay for compatibility during migration, but they are no longer the architectural center.

## What Is Deprecated

Deprecated as the primary way to explain or extend the product:

- stack-by-stack expansion as the top-level roadmap
- separate architecture narratives for triage versus core analysis
- documentation that treats ingress contracts or plugin contracts as the full architecture story

Those remain implementation details or compatibility layers, not the canonical system model.

## Rollout Strategy

1. Introduce a profile registry without changing current outputs.
2. Reframe the existing shipped behavior as `code_risk`.
3. Add shared trust scoring.
4. Add `ui_flow_risk` as a targeted changed-journey profile.
5. Add `business_invariant_risk` using repository-owned invariants.

## Recommended Architecture Decision

Keep the existing shared pipeline and evolve the product into a profile-based, capability-aware merge-risk system.

## Top 3 Implementation Actions

1. Add a thin profile registry above the current collectors/signals/rules pipeline and move the existing shipped behavior under `code_risk`.
2. Add a shared trust layer for confidence and precision scoring across all findings.
3. Add new profiles only as optional packs (`ui_flow_risk`, `business_invariant_risk`), never as separate pipelines or products.
