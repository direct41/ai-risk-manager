# AI Risk Manager

Know what to test before merging risky or AI-generated PRs.

AI Risk Manager is a PR-native release-risk assistant for engineering and QA teams. It scans a repository or PR branch, highlights high-risk changed areas, and writes a short test-first triage package.

It starts with deterministic evidence. AI enrichment is optional.

Use it if you review backend-heavy PRs, adopt AI-generated code, or want a short "what should we test first?" checklist before merge.

Do not use it as a SAST replacement, full business-logic verifier, or automatic release approval system.

## Start Here

Try the bundled demo in about a minute:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "git+https://github.com/direct41/ai-risk-manager.git"

riskmap analyze --sample --no-llm --analysis-engine deterministic --output-dir ./.riskmap
cat .riskmap/merge_triage.md
cat .riskmap/report.md
```

You should see:

- a merge decision: `ready`, `review_required`, or `block_recommended`
- the top risky areas
- the first tests or review checks to run

## Run On Your Repo

From the repository you want to inspect:

```bash
riskmap analyze \
  --mode full \
  --analysis-engine deterministic \
  --no-llm \
  --output-dir ./.riskmap
```

Read these first:

```bash
cat .riskmap/merge_triage.md
cat .riskmap/report.md
```

For PR-focused review:

```bash
riskmap analyze \
  --mode pr \
  --base main \
  --analysis-engine deterministic \
  --no-llm \
  --only-new \
  --output-dir ./.riskmap
```

For stronger PR delta attribution, create a baseline on `main` first:

```bash
riskmap analyze \
  --mode full \
  --analysis-engine deterministic \
  --no-llm \
  --output-dir ./.riskmap/baseline
```

Then run the PR branch with:

```bash
riskmap analyze \
  --mode pr \
  --base main \
  --baseline-graph ./.riskmap/baseline/graph.json \
  --only-new \
  --output-dir ./.riskmap
```

The baseline directory must contain both `graph.json` and `findings.json`.

## Good Fit

AI Risk Manager is currently best for:

- backend-heavy FastAPI, Django/DRF, and Express/Node repositories
- teams reviewing fast-moving or AI-generated PRs
- engineers who want test-first release-risk guidance before merge
- advisory CI checks before adopting blocking gates

It is not yet a good fit if you need:

- a generic SAST replacement
- full business-logic verification without repo-owned invariants
- broad UI screenshot diffing or cross-browser testing
- production release approval without human review

## What It Produces

The most useful files are:

- `.riskmap/merge_triage.md` - 10-minute merge decision and test-first order
- `.riskmap/report.md` - human-readable findings and top actions
- `.riskmap/findings.json` - machine-readable findings
- `.riskmap/test_plan.json` - prioritized test recommendations

PR mode can also produce:

- `.riskmap/pr_summary.md`
- `.riskmap/pr_summary.json`
- `.riskmap/github_check.json`

## Example Output

```md
# Merge Risk Triage

- Decision: `review_required`
- Headline: Run a focused 10-minute risk review before merge; risk score `61`.
- Risk score: `61/100`

## Test First

1. [high] `critical_path_no_tests` at `app/main.py:31`
   Action: Add API/service tests for endpoint 'POST /orders', including success and error paths.
```

## GitHub PR Comment

Generate a PR summary locally:

```bash
riskmap analyze \
  --mode pr \
  --base main \
  --only-new \
  --output-dir ./.riskmap
```

Publish it to GitHub:

```bash
export GITHUB_TOKEN=...
riskmap publish-pr-comment \
  --repo owner/repo \
  --pr-number 123 \
  --summary-file ./.riskmap/pr_summary.md
```

A copy-paste GitHub Actions example is available at `examples/github-actions/riskmap-pr-review.yml`.

## Current Scope

Shipped today:

- `code_risk`: supported release-risk review for code, tests, workflows, contracts, dependencies, and critical write paths
- `ui_flow_risk`: discovery-focused UI review with optional repo-declared smoke commands
- `business_invariant_risk`: explicit critical-flow checks through `.riskmap.yml`

Strongest stack support:

- `fastapi_pytest`
- `django_drf`
- `express_node`

Unknown stacks fall back to partial advisory support with universal heuristics.

## Feedback

AI Risk Manager is in limited open alpha.

Useful feedback includes:

- repository stack and shape
- command you ran
- top 3 findings
- which findings were useful or noisy
- what important risk was missed
- whether setup or wording blocked you

Use the [alpha feedback issue template](https://github.com/direct41/ai-risk-manager/issues/new?template=alpha_feedback.yml) or see `ALPHA.md`.

## Development

From a source checkout:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'

make test
make analyze-demo
```

## Docs

- `ALPHA.md` - concise alpha-user guide
- `docs/ru.md` - Russian quickstart
- `docs/workspaces.md` - workspace and monorepo usage
- `docs/business-invariants.md` - `.riskmap.yml` critical-flow checks
- `docs/ui-flow-pilots.md` - UI flow pilot notes
- `docs/architecture.md` - architecture overview
- `docs/roadmap.md` - roadmap and scope guardrails
- `docs/deployment-hardening.md` - API deployment hardening
- `docs/launch/product-hunt.md` - Product Hunt launch kit

## Open Source

- License: `LICENSE` (MIT)
- Contributing: `CONTRIBUTING.md`
- Security Policy: `SECURITY.md`
- Changelog: `CHANGELOG.md`
