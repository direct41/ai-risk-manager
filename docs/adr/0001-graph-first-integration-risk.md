# ADR 0001: Graph-First Integration and E2E Risk Analysis

- Date: 2026-06-22
- Status: Accepted

## Context

The original product direction was architecture-aware integration and E2E risk analysis. Over time, capability
signals and narrow PR heuristics became the dominant rule input. The graph remained an output artifact but stopped
being the canonical model for most decisions. That direction reduces differentiation from generic code-review and
static-analysis products.

## Decision

The canonical analysis flow is:

```text
Collectors -> evidence signals -> architecture graph -> impacted paths -> findings -> test plan
```

Collectors own stack syntax. Signals are normalized evidence and may not become a parallel business-rule model.
The graph owns architecture entities, state transitions, persistence, external effects, and test coverage. Generic
rules added after this ADR must operate on graph nodes, edges, or paths. Existing signal-only rules remain frozen as
compatibility behavior and may be migrated incrementally.

The first vertical slice is a FastAPI write path containing:

```text
API -> request Entity -> handled Transition -> DataStore / ExternalSystem
TestCase -(covered_by)-> API
```

A complete path without integration or E2E coverage emits `critical_flow_no_integration_tests`. Generated Mermaid
artifacts expose entity relationships and state transitions for review and debugging.

## Alternatives Considered

1. Continue adding signal-only rules. Fastest delivery, but preserves the generic-scanner trajectory.
2. Rewrite the analyzer around a new graph engine. Cleaner end state, but unnecessary churn and compatibility risk.
3. Evolve the existing graph and collectors in place. Chosen because it preserves shipped behavior and evaluation
   assets while restoring the original product boundary.

## Consequences

- New stack support maps syntax into the same graph vocabulary.
- Graph schema additions are backward-compatible; existing fields and artifacts remain.
- High-confidence extraction is intentionally narrow. Unsupported architecture facts stay absent rather than guessed.
- Generic signal-only rule growth requires superseding this ADR.
- Mermaid diagrams are review artifacts, not an independent source of truth.

## Rollout

1. Ship the FastAPI vertical slice and architecture fitness tests.
2. Validate path precision on public PRs and real repositories.
3. Add Django/Express parity only after repeated evidence justifies each extractor.
4. Migrate valuable legacy rules to path queries when their inputs exist in the graph.

## Rollback

Disable the new graph rule and stop emitting the additive Mermaid artifacts. Existing signal-only rules and JSON
contracts remain operational.
