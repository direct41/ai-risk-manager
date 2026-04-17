# AI Risk Manager

Find the highest-risk changes before merge and show the first checks to run.

AI Risk Manager is a PR-native merge-risk assistant.
It answers three practical questions:

- Which changed areas look risky right now?
- Which tests should we add first?
- Is this PR ready to merge, or does it need short release-risk review?

The current shipped profile is `code_risk`.
It works best on backend-heavy codebases and currently has strongest support on FastAPI, Django/DRF, and Express/Node repositories.

## Why AI Risk Manager?

- Focuses on merge and release risk instead of generic scanner noise.
- Produces a short PR triage package instead of another long report.
- Prioritizes test actions, not just findings.
- Starts with deterministic evidence; AI is optional.
- Still provides useful heuristics on unknown stacks.
- Expands by risk profiles, not by multiplying product variants.

## Architecture

The canonical architecture is now profile-based and capability-aware:

- one shared pipeline for collection, signals, rules, scoring, triage, and reporting
- optional risk profiles activated only when relevant
- profile applicability described as `supported`, `partial`, or `not_applicable`
- one output contract for reports and PR summaries

Current profiles:

- `code_risk` — shipped today
- `ui_flow_risk` — shipped as discovery-only review focus with optional declared browser smoke
- `business_invariant_risk` — explicit critical-flow checks through `.riskmap.yml`

See:

- `docs/architecture.md`
- `docs/roadmap.md`

## Install

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

## Try In 60 Seconds

Run the bundled deterministic demo:

```bash
make install
make analyze-demo
cat .riskmap/report.md
cat .riskmap/merge_triage.md
```

The demo does not call an LLM. It should finish quickly and produce a small report with concrete test-first actions.

## Quick Start

Run the trust-first deterministic path on your repository:

```bash
riskmap analyze \
  --mode full \
  --analysis-engine deterministic \
  --no-llm \
  --output-dir ./.riskmap
```

Open the main report:

```bash
cat ./.riskmap/report.md
cat ./.riskmap/merge_triage.md
```

If you want to try the bundled sample first:

```bash
riskmap analyze --sample --no-llm --analysis-engine deterministic --output-dir ./.riskmap
```

## Example Output

```md
# Risk Analysis Report

## Summary

| Severity | Count |
|---|---:|
| critical | 0 |
| high | 1 |
| medium | 1 |
| low | 0 |

## Top Actions for Next Sprint

- Add API/service tests for endpoint 'POST /orders', including success and error paths.
- Implement handler logic for transition 'pending -> cancelled' or remove stale declaration.
```

## What You Get

- `report.md`: human-readable summary and top actions
- `merge_triage.md`: 10-minute merge decision, reasons, and test-first order
- `findings.json`: machine-readable findings, including additive trust metadata
- `merge_triage.json`: machine-readable merge triage package
- `test_plan.json`: prioritized test recommendations
- `run_metrics.json`: machine-readable run quality and execution metrics
- PR mode also writes `pr_summary.md`, `pr_summary.json`, and `github_check.json`; these include active profile applicability and compact trust data for top findings. JSON output also includes graph artifacts (`graph.json`, `graph.analysis.json`, `graph.deterministic.json`)

For all flags and modes:

```bash
riskmap analyze --help
```

## PR Workflow

Create a deterministic baseline on `main`:

```bash
riskmap analyze \
  --mode full \
  --analysis-engine deterministic \
  --no-llm \
  --output-dir ./.riskmap/baseline
```

Run PR-scoped analysis on your feature branch:

```bash
riskmap analyze \
  --mode pr \
  --base main \
  --baseline-graph ./.riskmap/baseline/graph.json \
  --only-new \
  --output-dir ./.riskmap
```

For PR delta to work, the baseline directory must contain both `graph.json` and `findings.json`.

Publish the generated PR summary back to GitHub:

```bash
export GITHUB_TOKEN=...
riskmap publish-pr-comment \
  --repo owner/repo \
  --pr-number 123 \
  --summary-file ./.riskmap/pr_summary.md
```

A copy-paste GitHub Actions example is available at `examples/github-actions/riskmap-pr-review.yml`.
An optional UI smoke manifest example is available at `examples/ui/.riskmap-ui.toml`.
Nuxt checkout/product/cart examples are available at `examples/ui/nuxt/.riskmap-ui.toml`.
The PR summary includes grouped `.airiskignore` suppression hints for intentional risk acceptance, plus changed-file-aware top risks, trust metadata, active profile applicability, changed UI journey review focus when a web surface is detected, and declared browser smoke failures as normal findings.

Optional `ui_flow_risk` smoke config:

```toml
[[journeys]]
id = "checkout"
match = ["checkout", "billing"]
command = ["npm", "run", "test:e2e", "--", "checkout"]
```

Place it in `./.riskmap-ui.toml`. The command runs only for changed UI journeys that match a declared entry.

For workspaces or monorepos, run analysis from the package that owns the changed app. See `docs/workspaces.md`.

## Alpha Testing

AI Risk Manager is ready for limited open alpha with teams that:

- review fast-moving PRs and want a short release-risk checklist
- use AI-generated code and need to know what to test first
- can run a CLI locally or in GitHub Actions
- are comfortable with advisory output before adopting blocking CI gates

Best feedback to send:

- repository type and stack
- whether the top 3 findings were useful or noisy
- what test you added or skipped because of the report
- any false positive, missing risk, or confusing instruction

See `ALPHA.md` for a concise alpha-user guide.

## Works Best For

- backend teams doing pre-merge or pre-release reviews
- repositories where release risk is mostly in code, tests, workflows, contracts, and privileged paths
- teams that want advisory signals before enabling CI gates
- teams reviewing fast AI-generated code and deciding what to test first

## Current Scope

- Shipped profile: `code_risk`
- Discovery-only profile: `ui_flow_risk`
- Stack plugins with strongest coverage: `fastapi_pytest`, `django_drf`, `express_node`
- Universal heuristics on unknown stacks: PR delta signals, workflow automation checks, generated test quality checks, dependency policy checks
- UI profile behavior: detect whether a UI surface exists, including vanilla `public/` or `static/` app shells, mark API-only repositories as `not_applicable`, surface changed route/component journeys in PR review focus, and optionally run declared journey smoke commands from `./.riskmap-ui.toml`
- Business invariant behavior: with explicit `.riskmap.yml` / `.riskmap.yaml`, flag declared critical-flow changes that lack a matching changed check file
- Merge triage: `ready`, `review_required`, or `block_recommended` with a short test-first order

## Limits

- Not a generic multi-language SAST replacement
- Not a full business-logic verifier; current invariant support is limited to declared critical-flow PR deltas
- `ui_flow_risk` only runs declared journey smoke commands; it is not a generic browser runner, screenshot diff system, or cross-browser matrix
- Unknown stacks fall back to partial `code_risk` support with universal heuristics
- Merge triage is an evidence-backed review aid, not an automatic release approval

## API

If you need a local API service:

```bash
pip install -e '.[api]'
riskmap-api
```

Optional hardening is available through environment variables such as `AIRISK_API_TOKEN`, `AIRISK_API_RATE_LIMIT_PER_MINUTE`, and `AIRISK_API_MAX_BODY_BYTES`.
If you need persistent API audit logging outside the output directory, set `AIRISK_API_AUDIT_LOG`.

## Development

```bash
make install
make test
make analyze-demo
```

## Docs

- `ALPHA.md`
- `docs/architecture.md`
- `docs/roadmap.md`
- `docs/workspaces.md`
- `docs/ui-flow-pilots.md`
- `docs/business-invariants.md`
- `docs/ru.md`
- `docs/compatibility.md`
- `docs/deployment-hardening.md`

Internal and compatibility notes:

- `docs/legacy-review.md`
- `docs/capability-signals.md`
- `docs/ingress-contract.md`
- `docs/plugin-contract.md`

## Open Source

- License: `LICENSE` (MIT)
- Contributing: `CONTRIBUTING.md`
- Security Policy: `SECURITY.md`
- Changelog: `CHANGELOG.md`
