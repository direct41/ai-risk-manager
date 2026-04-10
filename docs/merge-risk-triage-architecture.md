# Merge Risk Triage Architecture

## Product Goal

AI Risk Manager should help a backend team answer a practical pre-merge question:

> What is risky in this change, what should we test first, and is this safe enough to merge?

The product should optimize for a 10-minute review loop, not for exhaustive static analysis.

## Pain-To-Architecture Mapping

| User pain | Architecture response |
|---|---|
| Before merge, it is unclear which changes are risky. | Keep PR mode and baseline delta, then summarize the result as a merge decision. |
| AI generates code fast, but testing does not keep up. | Convert findings into a test-first order with concrete assertions and a short time budget. |
| There may be too many or too few tests, and priority is unclear. | Rank test actions by release-risk score, not by file order or generic coverage. |
| Review catches style but misses release risk. | Add a downstream triage layer that explains why each action matters for release safety. |
| Regression after release costs more than short pre-merge triage. | Emit `merge_triage.md` and `merge_triage.json` as the primary review artifacts. |

## Architecture Decision

Add `triage` as a downstream decision layer.

The existing architecture remains evidence-first:

1. Collectors extract stack-specific artifacts.
2. Signals normalize framework details into common contracts.
3. Graph and rules produce evidence-backed findings.
4. QA strategy turns findings into test recommendations.
5. Merge triage turns findings plus test recommendations into a decision package.

The triage layer must not own extraction, rule detection, or AI claims. Its job is to make already-evidenced risk usable during PR review.

## Module Boundary

New module:

- `ai_risk_manager.triage`

Responsibilities:

- rank findings by release-risk relevance;
- map findings to available test recommendations;
- produce a merge decision;
- keep output short enough for pre-merge review;
- emit deterministic Markdown and JSON artifacts.

Non-responsibilities:

- parse source code;
- create new findings;
- decide stack support;
- bypass evidence verification;
- replace CI policy.

## Decision Model

`merge_triage.decision` has three values:

| Decision | Meaning |
|---|---|
| `ready` | No active evidence-backed release-risk action is required for the current scope. |
| `review_required` | A human should run the recommended short triage before merge. |
| `block_recommended` | The PR should not merge before the top release-risk action is handled. |

The current decision inputs are:

- finding severity;
- confidence;
- PR status (`new`, `unchanged`, `resolved`);
- evidence refs;
- effective CI mode;
- analysis scope (`impacted`, `full`, `full_fallback`);
- repository support state;
- verification and evidence completeness.

## Release-Risk Score

The score is intentionally simple and explainable. It prioritizes:

- new findings over unchanged findings;
- high/critical findings over medium/low findings;
- higher-confidence findings;
- findings with evidence refs;
- deterministic findings over AI-only findings.

This is not a probability of release failure. It is a sorting mechanism for pre-merge attention.

## Artifact Contract

The triage layer writes:

- `merge_triage.md`: human-readable decision, reasons, and test-first order;
- `merge_triage.json`: machine-readable decision package.

The main `report.md` and PR summary also include the merge decision and top test-first actions.

## Why This Improves The Product

The project previously had strong evidence mechanics but weak decision packaging. A user could see findings and a test plan, but still had to decide:

- what to test first;
- whether the PR is risky enough to stop;
- whether fallback or partial support weakens confidence;
- how to explain the risk in review.

`merge_triage` makes that decision explicit without expanding stack scope.

## Evolution Path

Near-term improvements should deepen triage quality before adding more stacks:

1. Add changed-surface context to each triage action.
2. Track whether recommended tests were added after the report.
3. Add suppression reason hygiene to distinguish accepted risk from false positive.
4. Add PR-comment templates optimized for GitHub review.
5. Use real repository runs to calibrate the score and decision thresholds.

Stack expansion should wait until the triage package proves useful on current supported stacks and advisory L0 repositories.
