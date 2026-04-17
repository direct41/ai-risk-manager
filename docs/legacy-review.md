# Legacy Review

This review identifies current candidates for deletion or demotion after the profile-based architecture has landed.

The rule used here is simple:

- delete now if a document only adds confusion
- keep for now if runtime depends on it
- mark as compatibility-only if it still works but no longer defines the product direction

## Immediate Removals

These documents were useful during earlier design stages but should not remain as active architecture guidance.
They have been removed from the repository root or replaced by canonical docs:

- `docs/architecture-next.md`
- `docs/merge-risk-triage-architecture.md`
- `docs/stack-expansion-candidates.md`
- `ROADMAP.md`
- `PLAN.md`
- `PLAN_UNIVERSAL_AI.md`
- `BACKLOG_TRUST_FIRST.md`

Reason:

- they describe partial historical directions
- they duplicate or conflict with the new canonical architecture
- they encourage stack-centric thinking as the primary expansion model

## Compatibility-Only Code Candidates

These are not deletion targets today because the runtime still depends on them.
They are candidates to retire after alpha feedback confirms the profile-based output is stable.

### 1. Stack-first selection path

Files:

- `src/ai_risk_manager/stacks/discovery.py`
- `src/ai_risk_manager/collectors/plugins/registry.py`
- stack selection logic inside `src/ai_risk_manager/pipeline/run.py`

Why it is legacy:

- it treats repository analysis as "pick one stack plugin first"
- the new architecture treats analysis as "activate relevant risk profiles"

Deletion trigger:

- once `code_risk` no longer needs stack plugin selection and all stack-specific behavior is behind profile-owned adapters

### 2. Plugin contract v1 surface

Files:

- `src/ai_risk_manager/collectors/plugins/contract.py`
- `src/ai_risk_manager/collectors/plugins/sdk.py`
- `src/ai_risk_manager/collectors/plugins/scaffold.py`

Why it is legacy:

- it is designed around stack-plugin expansion as the primary scaling path
- future expansion should happen through profiles and capability packs

Deletion trigger:

- once `code_risk` owns its own compatibility contract and new profiles no longer depend on stack-plugin scaffolding

### 3. Repository-wide support semantics

Files:

- summary/report fields in `src/ai_risk_manager/schemas/types.py`
- repository-wide support decisions in `src/ai_risk_manager/pipeline/run.py`

Fields:

- `support_level_applied`
- `repository_support_state`

Why it is legacy:

- support is currently described for the whole repository
- the target model needs profile-level applicability:
  - `supported`
  - `partial`
  - `not_applicable`

Deletion trigger:

- once summaries expose profile-level applicability directly

### 4. Reporting-era compatibility metadata

Files:

- `src/ai_risk_manager/schemas/types.py`
- `src/ai_risk_manager/pipeline/run.py`
- API response models

Fields:

- `competitive_mode`
- `graph_mode_applied`

Why it is legacy:

- they reflect previous internal staging decisions
- they are weak user-facing concepts for the new architecture

Deletion trigger:

- once no user workflow or API consumer depends on them

## Keep

These modules are still aligned with the target architecture and should stay:

- `collectors`
- `signals`
- `rules`
- `triage`
- `reports`
- `pipeline`
- `integrations/github_pr_comments.py`
- `collectors/plugins/universal_artifacts.py`
- `pipeline/pr_change_signals.py`

Reason:

- they already fit the shared-pipeline model
- they should be reused under the new profiles instead of replaced

## Review Summary

The product does not need a rewrite.
It needs:

- continued removal of stale architecture documents
- demotion of stack-plugin contracts to compatibility status
- eventual retirement of stack-first runtime selection after real alpha feedback confirms profile behavior

## Recommended Next Actions

1. Keep `README.md`, `ALPHA.md`, and `docs/roadmap.md` as the public planning sources of truth.
2. Treat stack-plugin contracts as compatibility-only in docs and avoid expanding the public product around them.
3. Do not delete runtime stack-selection code until alpha users confirm profile-level output is useful and stable.
