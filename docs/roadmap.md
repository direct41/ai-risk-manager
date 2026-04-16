# Roadmap

This roadmap assumes fast iterative delivery, small PRs, and continuous documentation cleanup.

The goal is not a large rewrite. The goal is to migrate the existing product into the new architecture with minimal churn.

## Delivery Style

How to implement this through "vibe coding" without losing control:

- keep one architectural direction document open while coding
- ship thin slices that preserve existing behavior
- prefer extraction and refactoring over parallel subsystems
- every slice must end with green `ruff`, `mypy`, and `pytest`
- update docs in the same PR as code

## Release 1: Profile Registry

Goal:

- introduce the new architectural frame without breaking the current runtime

Implementation:

- add a `profiles` package with a registry and selection contract
- register a single shipped profile: `code_risk`
- keep current collectors/rules/reporting behavior unchanged
- map current stack-plugin/universal logic under `code_risk`

Done when:

- current output artifacts do not change materially
- docs no longer describe the product as stack-expansion-first

Status:

- implemented

## Release 2: Trust Layer

Goal:

- make false-positive handling explicit and measurable

Implementation:

- add `trust/scoring.py`
- add `trust/outcomes.py`
- define scoring inputs:
  - rule precision
  - support/applicability level
  - evidence richness
  - suppression history
- expose confidence and precision bands in machine-readable artifacts first

Done when:

- findings have a clearer trust story
- suppression data can be used to tune noisy rules

Status:

- implemented at finding level

## Release 3: Profile-Aware Summary and Trust Visibility

Goal:

- make profile applicability and trust change PR review behavior instead of staying latent in JSON only

Implementation:

- expose active profile applicability in `report.md`, `pr_summary.md`, `pr_summary.json`, and `github_check.json`
- expose compact trust data for top findings in PR-facing artifacts
- keep changes additive and backward-compatible

Done when:

- PR-facing output shows which profile actually ran
- top findings carry compact trust metadata in human and machine-readable summaries

Status:

- implemented

## Release 4: `ui_flow_risk` MVP

Goal:

- cover visual regression, UX breakage, and browser-risk pain without turning the product into a generic UI test runner

Implementation:

- detect whether the repository has a UI surface
- map changed files to routes/pages/components
- define a small journey manifest for critical flows
- run targeted browser checks only for declared changed journeys
- emit evidence-backed findings and review focus

Scope guardrails:

- no full browser matrix for every PR
- no whole-site visual snapshot spam
- only top journeys and changed scope

Done when:

- a UI-heavy repository gets useful PR output
- an API-only repository sees `ui_flow_risk = not_applicable`

Status:

- discovery and changed-journey mapping implemented
- declared smoke execution for changed journeys implemented
- vanilla `public/` and `static/` app shells detected after real-repo pilot
- screenshot diffing and cross-browser execution still pending

## Pilot-Derived Backlog

Source:

- real pilot against `projects/notes-buggy-pet`
- real pilot against `work/rnd-autotests/1win-shop`

Decisions:

- keep fixes small and evidence-quality driven
- prefer better labels and targeted scope over broader scanners
- do not add browser matrices or business-rule inference until profile trust improves
- treat multi-package workspaces as separate project roots until workspace discovery is intentionally designed

Priority backlog:

| Priority | Item | Why | Status |
|---|---|---|---|
| P0 | Show real Express route labels for wrapped handlers such as `asyncRoute(...)` | Findings must point reviewers to `POST /api/login`, not implementation wrappers | implemented |
| P1 | Improve PR summary relevance so changed-scope risks outrank unrelated repo-wide findings | UI-only diffs should not be dominated by unchanged dependency policy findings | implemented |
| P1 | Provide a copy-paste `.riskmap-ui.toml` example for vanilla app shells | Early users need the shortest path to opt-in browser smoke | implemented |
| P1 | Normalize Nuxt/Vue route and component labels | Review focus should say `checkout`, `product/[slug]`, or `cartmodal`, not `checkout/vue` or route-like component noise | implemented |
| P1 | Cap repeated repo-wide findings in PR summary when changed scope is known | PR comments should not look like generic scanner output when full findings remain available elsewhere | implemented |
| P2 | Validate `ui_flow_risk` on 2-3 more real frontend layouts before screenshot diffing | Avoid generic noisy scanner behavior | implemented |
| P2 | Add workspace/monorepo invocation guidance | `1win-shop` root is not a single git repo; each package should be analyzed at its own project root for now | implemented |
| P2 | Add declared smoke examples for Nuxt checkout/product/cart journeys | Real Nuxt projects need a short path from review focus to executable smoke checks | implemented |
| P2 | Start `business_invariant_risk` only with explicit repo-owned specs | Teams want business logic checks, but implicit guessing would be untrustworthy | first critical-flow rule implemented |

## Release 5: `business_invariant_risk` MVP

Goal:

- support teams that expect business-logic checks without pretending the tool can infer business rules from code alone

Implementation:

- add repository-owned `.riskmap.yml`
- define sections for:
  - critical flows
  - state invariants
  - auth/payment/admin invariants
  - must-have negative paths
- add a small first rule pack that checks conformance around declared invariants

Scope guardrails:

- no free-form AI business interpretation
- no hidden implicit rules
- if no invariant spec exists, mark the profile `not_applicable`

Done when:

- teams can encode a few high-value domain rules and see them enforced in PR review

Status:

- profile scaffold implemented
- explicit `.riskmap.yml` / `.riskmap.yaml` detection implemented
- first deterministic critical-flow rule implemented:
  - `business_critical_flow_changed_without_check_delta`
  - PR-only
  - based on declared `critical_flows[].match` and `critical_flows[].checks`
- state/auth/payment/admin invariant rules pending

## Release 6: Compatibility Cleanup

Goal:

- remove compatibility layers that are no longer architecturally useful

Implementation:

- retire stack-first documentation
- shrink repository-wide support semantics in favor of profile applicability
- demote plugin contract v1 to a code-risk compatibility surface
- remove reporting-era fields that no longer drive decisions

Done when:

- the code and docs tell the same architectural story
- obsolete layers are either removed or clearly marked as compatibility-only

## PR Sequence

Recommended PR sequence:

1. docs-only architecture and roadmap reset
2. profile registry with `code_risk`
3. trust layer scaffolding
4. profile-aware summary/reporting
5. `ui_flow_risk` discovery and changed-journey mapping
6. targeted UI/browser checks
7. `.riskmap.yml` invariant spec
8. `business_invariant_risk` initial rules
9. compatibility cleanup and code deletion

## What Not To Build

- no GitHub App
- no separate service for each profile
- no second report generator
- no LLM-first business logic verifier
- no dashboard-first enterprise layer before trust is proven

## Recommended Next Actions

1. Start `ui_flow_risk` with repository discovery and changed-journey mapping only.
2. Keep browser execution opt-in and targeted to declared critical journeys.
3. Treat `ui_flow_risk` and `business_invariant_risk` as optional profiles, never as a new product branch.
