# Graph-First, Profile-Aware Architecture

## Decision

AI Risk Manager evolves as a single architecture-aware merge-risk pipeline with optional `risk profiles`.

The architecture graph is the canonical model for generic risk decisions. Collectors normalize stack syntax into
evidence signals; the graph connects ingress, entities, states, persistence, external effects, and tests. Profiles
select relevant graph surfaces and may add explicitly scoped repository-owned checks.

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
4. Signals build the canonical architecture graph and impacted paths.
5. Shared generic rules evaluate graph structure and coverage into findings.
6. Shared scoring and triage rank findings for merge review.
7. Shared report generation emits reports plus entity/state Mermaid artifacts.

Current runtime note:

- shipped PR-facing summaries already expose active profile applicability and compact trust metadata for top findings

One graph. Multiple profiles. One output contract.

See `docs/adr/0001-graph-first-integration-risk.md` for the decision and migration constraints.

## Core Runtime

The current code already has the right core modules:

- `collectors`
- `signals`
- `graph`
- `rules`
- `triage`
- `reports`
- `pipeline`

Those remain the center of the system. `signals` are evidence ingress; `graph` owns the canonical architecture model;
generic `rules` query graph structure and path coverage. Existing signal-only rules are frozen compatibility behavior.

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
| --- | --- | --- | --- |
| API-only service | supported | not_applicable | partial or not_applicable |
| SaaS web app | supported | partial/supported | partial |
| Worker/ETL repo | partial | not_applicable | not_applicable |

This is the correct abstraction for heterogeneous products.

## Trust Layer

Every finding should be evaluated through the same trust model:

- evidence strength
- support/applicability level
- observed accepted, suppressed, and actioned outcomes
- repository suppression history

This is a shared heuristic scoring layer, not a calibrated probability model and not statistical precision. Calibration remains blocked until the frozen holdout has independent human labels.

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

1. Ship the FastAPI graph-first write-flow slice without removing compatibility behavior.
2. Validate entity, transition, persistence, external-system, and test edges on real repositories.
3. Add Django/Express parity only when extraction evidence is high-confidence.
4. Migrate valuable legacy signal-only rules into graph path rules incrementally.
5. Keep profiles as graph views and explicitly scoped repository-owned checks.

## Recommended Architecture Decision

Keep the existing shared pipeline and make the architecture graph the source of truth for integration/E2E risk.

## Top 3 Implementation Actions

1. Validate the FastAPI full write-flow extractor against real repositories and public PRs.
2. Add repository-level coverage edges for service and browser journeys without guessing unsupported facts.
3. Migrate one repeated legacy risk family to graph-path evaluation before adding another generic rule.
