# Next Architecture Direction

## Current State

Facts:

- Core pipeline is already shared across `CLI` and `HTTP API`.
- Collector plugins are implemented for `fastapi_pytest`, `django_drf`, and `express_node`.
- Core deterministic risk logic is organized around shared capability signals, not stack-specific rule families.
- Stage 11 capability packs and Stage 12 pack-promotion gates are complete.

This means the project has crossed the original MVP boundary. The next risk is no longer "can we ship another rule?" but "can we keep scaling without multiplying stack-specific complexity?"

## Architecture Goal

Keep the analyzer universal in its core:

- plugins adapt stack syntax to a common contract;
- core rules remain stack-agnostic;
- AI is used to widen extraction coverage, but only behind evidence and verification boundaries;
- new product scope grows by ingress and capability contracts, not by ad hoc rule forks.

## Constraints

- The system must stay explainable and trust-first.
- Blocking or promotion decisions must remain evidence-backed and deterministic.
- New supported scenarios must fit the existing plugin contract and eval gate model.
- Repository structure must remain understandable to humans before it is convenient for automation.

## Candidate Directions

### Option A: Keep expanding stack-by-stack

Description:

- Add more frameworks and more stack-specific heuristics directly where needed.

Why not:

- This recreates the same scaling problem the project was trying to escape.
- Core complexity grows faster than capability coverage.
- Trust becomes harder to measure because behavior diverges by stack.

### Option B: Keep current stacks, deepen only `express_node`

Description:

- Continue shipping more capability packs only for the richest current plugin.

Why not:

- Good for local precision, bad for product direction.
- The project would become "best effort for one stack, partial elsewhere."
- It delays the real architectural question: how capabilities move across stacks.

### Option C: Standardize on ingress families plus portable capability packs

Description:

- Treat project analysis through two stable dimensions:
  - ingress family
  - capability pack
- Make plugins responsible for mapping syntax to shared ingress and capability contracts.

Why this is the recommended option:

- It scales better than framework-by-framework branching.
- It matches the current architecture direction already present in code.
- It gives a clean path for AI-assisted extraction without weakening trust gates.

## Decision Summary

The next development wave should be organized around:

1. Ingress contracts
2. Portable capability parity
3. Evidence-bound AI extraction

In practical terms:

- `HTTP` should stop being the implicit center of the product model.
- The analyzer should explicitly support multiple sink families:
  - HTTP endpoint
  - webhook handler
  - background job
  - event consumer
  - CLI/task entrypoint
- Capability packs should then attach to those sinks where they make sense.

## Deep Module Map

Current stable deep modules:

- `collectors/plugins`
  - stack adapters
- `signals`
  - common capability language
- `graph`
  - normalized topology and evidence references
- `rules`
  - deterministic risk logic
- `agents`
  - AI enrichment and semantic analysis
- `pipeline`
  - orchestration and rollout behavior

Recommended next deep modules or responsibilities:

- `signals`
  - extend from capability-only view to ingress-family plus capability view
- `collectors/plugins`
  - expose sink-normalized extraction, not only framework facts
- `schemas`
  - own explicit ingress contract types
- `eval`
  - promote by capability parity across stacks and sink families

No new top-level package is required yet. The current repository structure can absorb the next phase without structural churn.

## Boundary Design

### Sink boundary

Every plugin should normalize raw framework constructs into a common ingress contract before they reach core rules.

Target ingress concepts:

- `http_write_surface`
- `webhook_surface`
- `job_execution_surface`
- `event_consumer_surface`
- `cli_mutation_surface`

### Capability boundary

Capability packs should stay portable and composable.

Examples:

- authorization boundary
- side-effect contract
- write contract integrity
- session lifecycle consistency
- render safety

### AI boundary

AI extraction must remain advisory until verified.

Rules:

- no evidence -> drop
- no schema match -> drop
- no deterministic anchor -> advisory only

## Interaction Model

Recommended sequencing:

1. Plugin extracts sink surfaces and candidate capability evidence.
2. Core normalizes them into common signal contracts.
3. Deterministic rules run on normalized signals.
4. AI may enrich or recover partial relations, but never bypasses verification.
5. Eval gates decide promotion at stack and capability-pack level.

## Repository Plan

Near-term repository changes should stay incremental:

- add ingress contract types under `schemas` or `signals`;
- extend plugin adapters to emit those contracts;
- keep `rules` free of framework conditionals;
- keep promotion logic centralized in eval artifacts, not spread across runtime code.

## Risks And Mitigations

1. Risk: ingress model becomes too abstract and loses practical value.
   Mitigation: start with only the sink families already close to current product behavior.

2. Risk: AI extraction reintroduces noisy findings on unsupported stacks.
   Mitigation: advisory-only support level for AI-assisted generic extraction until parity gates exist.

3. Risk: parity work across existing stacks becomes expensive.
   Mitigation: move capability packs one by one, not all at once, and keep promotion per-pack.

## Phased Rollout

### Phase 1: Ingress Contract Generalization

- define sink-family contracts beyond HTTP
- keep runtime behavior stable for existing stacks
- add eval coverage for new sink contracts

### Phase 2: Capability Parity Across Supported Stacks

- bring Stage 11 capability packs to `fastapi_pytest` and `django_drf`
- promote each pack independently using existing gate model

### Phase 3: AI-Assisted Generic Extraction

- add evidence-bound generic extraction for partially supported repositories
- keep generic mode advisory until trust metrics justify promotion

### Phase 4: External Plugin Distribution

- only if real adoption pressure appears
- package plugin SDK and external plugin loading story after contracts are stable

## Final Recommendation

Adopt Option C: organize future work around ingress-family contracts plus portable capability packs, with AI used as a verified extraction assistant rather than as the source of truth.

## Top 3 Implementation Actions

1. Define and version common ingress contracts beyond HTTP.
2. Move Stage 11 capability packs from `express_node`-only to parity across existing supported stacks.
3. Design advisory-only AI extraction for partially supported repositories behind explicit trust gates.
