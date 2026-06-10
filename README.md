# AI Risk Manager

> PR-native release-risk assistant that tells engineering and QA teams what to test before merging risky or AI-generated code.

[![Quality Gates](https://github.com/direct41/ai-risk-manager/actions/workflows/quality.yml/badge.svg)](https://github.com/direct41/ai-risk-manager/actions/workflows/quality.yml)
[![Eval Suite](https://github.com/direct41/ai-risk-manager/actions/workflows/eval-suite.yml/badge.svg)](https://github.com/direct41/ai-risk-manager/actions/workflows/eval-suite.yml)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)
![Status](https://img.shields.io/badge/status-open%20alpha-orange)
![Analysis](https://img.shields.io/badge/analysis-deterministic--first-brightgreen)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Know what to test before merging risky or AI-generated PRs.

AI Risk Manager scans a repository or PR branch, highlights high-risk changed areas, and writes a short test-first triage package. It starts with deterministic evidence. AI enrichment is optional.

Use it if you review backend-heavy PRs, adopt AI-generated code, or want a short "what should we test first?" checklist before merge.

Do not use it as a SAST replacement, full business-logic verifier, or automatic release approval system.

Fastest proof path:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "git+https://github.com/direct41/ai-risk-manager.git"

riskmap review-pr https://github.com/OWNER/REPO/pull/123
cat .riskmap/review-pr-OWNER-REPO-123/merge_triage.md
cat .riskmap/review-pr-OWNER-REPO-123/pr_summary.md
```

The command clones the public GitHub PR into a temporary checkout, builds a baseline on the base branch, runs deterministic/no-LLM PR analysis by default, and writes artifacts locally.

Have one hard public PR? Use the [public PR review request template](https://github.com/direct41/ai-risk-manager/issues/new?template=pr_review_request.yml). The most useful alpha input is not a star; it is one real PR where the test-first output is useful, noisy, or wrong.

## Why This Exists

Fast-moving and AI-generated PRs often fail in the gap between "the code compiles" and "we know what release risk changed." Generic scanners can find security or style issues, but they usually do not tell a reviewer which API paths, write flows, tests, and invariants deserve attention before merge.

AI Risk Manager is built for that review moment. It gives engineering and QA teams a compact, evidence-backed answer: what changed, why it looks risky, and what to test first.

## At a Glance

| Capability | What it does |
|---|---|
| PR risk triage | Ranks risky changed areas before merge. |
| Deterministic-first analysis | Runs locally without sending repository snippets to an LLM by default. |
| Test-first output | Writes `merge_triage.md`, `report.md`, `findings.json`, and `test_plan.json`. |
| One-command PR review | Runs `riskmap review-pr <github-pr-url>` against a public GitHub PR. |
| Public PR benchmark | Runs `riskmap benchmark-prs` against a curated public PR corpus and checks expected outcomes. |
| Supported stacks | Strongest on FastAPI, Django/DRF, and Express/Node repositories. |
| Optional AI enrichment | Adds semantic findings only when explicitly enabled. |
| Advisory CI mode | Starts as a review aid before teams adopt stricter blocking gates. |
| Repo-owned invariants | Uses `.riskmap.yml` for critical-flow checks instead of guessing business rules. |

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

Review a public GitHub PR without manually checking out the branch:

```bash
riskmap review-pr https://github.com/OWNER/REPO/pull/123
```

Read these first:

```bash
cat .riskmap/review-pr-OWNER-REPO-123/merge_triage.md
cat .riskmap/review-pr-OWNER-REPO-123/pr_summary.md
```

For very large repositories, use `--skip-baseline` to trade faster setup for noisier `full_fallback` PR analysis.

Run the public PR benchmark corpus from this repository:

```bash
riskmap benchmark-prs eval/public_prs.json --output-dir .riskmap/public-pr-corpus
cat .riskmap/public-pr-corpus/benchmark_summary.md
```

Use `--case-id express-7287` for a single regression case while tuning output quality.

Inspect corpus labeling progress and validate label metadata:

```bash
riskmap corpus-status eval/public_prs.json --strict
cat .riskmap/public-pr-corpus-status/corpus_status.md
```

Run a blind Claude assessment against selected pending cases after producing benchmark artifacts:

```bash
riskmap judge-prs eval/public_prs.json \
  --benchmark-dir .riskmap/public-pr-corpus \
  --case-id fastapi-15676 \
  --model claude-sonnet-4-6
```

This optional workflow requires an installed and authenticated Claude Code CLI. Judge packets, raw responses, and normalized assessments stay under ignored `.riskmap/external-judge/`.

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

AI enrichment is opt-in. Deterministic analysis is the CLI default; use
`--analysis-engine hybrid` or `--analysis-engine ai-first` with an explicit
provider only when repository snippets are allowed to leave your machine or CI
runner.

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

## Quick Paths

| Goal | Start here |
|---|---|
| Try the product quickly | Run `riskmap analyze --sample --no-llm --analysis-engine deterministic`. |
| Review a public GitHub PR by URL | Use `riskmap review-pr https://github.com/OWNER/REPO/pull/123`. |
| Review a PR locally | Use `riskmap analyze --mode pr --base main --only-new`. |
| Add CI advisory review | Start from `examples/github-actions/riskmap-pr-review.yml`. |
| Add GitLab merge request review | Start from `examples/gitlab-ci/riskmap-merge-request-review.yml`. |
| Validate whether the tool is useful | Follow `docs/validation.md`. |
| Send one hard public PR | Open the `pr_review_request.yml` issue template. |
| Add domain checks | Read `docs/business-invariants.md` and define `.riskmap.yml`. |
| Use a monorepo | Read `docs/workspaces.md` and run one package root at a time. |
| Harden API deployment | Read `docs/deployment-hardening.md`. |

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

## How It Works

1. Detect repository shape and support level.
2. Collect stack-specific and universal evidence from code, tests, workflows, dependencies, and configured invariants.
3. Normalize evidence into capability signals.
4. Run deterministic rules first.
5. Optionally add AI semantic enrichment when explicitly enabled.
6. Score trust from evidence, support level, confidence, and suppression history.
7. Emit human-readable and machine-readable triage artifacts for local review or CI.

## GitHub PR Comment

Generate a PR summary locally:

```bash
riskmap analyze \
  --mode pr \
  --base main \
  --analysis-engine deterministic \
  --no-llm \
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

Copy-paste CI examples are available for GitHub Actions and GitLab CI:

- `examples/github-actions/riskmap-pr-review.yml`
- `examples/gitlab-ci/riskmap-merge-request-review.yml`

## Current Scope

Shipped today:

- `code_risk`: supported release-risk review for code, tests, workflows, contracts, dependencies, and critical write paths
- `ui_flow_risk`: discovery-focused UI review with repo-declared smoke commands only when `AIRISK_UI_SMOKE_ENABLE_COMMANDS=1`
- `business_invariant_risk`: explicit critical-flow checks through `.riskmap.yml`

Strongest stack support:

- `fastapi_pytest`
- `django_drf`
- `express_node`

Unknown stacks fall back to partial advisory support with universal heuristics.

## Feedback

AI Risk Manager is in limited open alpha.

Useful feedback includes:

- the PR URL you tried
- repository stack and shape
- command you ran
- top 3 findings
- which findings were useful or noisy
- what important risk was missed
- whether setup or wording blocked you

Use the [public PR review request template](https://github.com/direct41/ai-risk-manager/issues/new?template=pr_review_request.yml) if you have one hard public PR. Use the [alpha feedback issue template](https://github.com/direct41/ai-risk-manager/issues/new?template=alpha_feedback.yml) if you already ran the tool and want to share results.

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

- `docs/ru.md` - Russian quickstart
- `docs/validation.md` - 30-day validation playbook for testing product value
- `docs/validation-results.md` - public-safe template for tracking external validation runs
- `docs/workspaces.md` - workspace and monorepo usage
- `docs/business-invariants.md` - `.riskmap.yml` critical-flow checks
- `docs/deployment-hardening.md` - API deployment hardening
- `docs/compatibility.md` - CLI/API/artifact compatibility policy
- `docs/plugin-contract.md` - plugin author contract
- `docs/ingress-contract.md` - ingress signal contract

## Open Source

- License: `LICENSE` (MIT)
- Contributing: `.github/CONTRIBUTING.md`
- Security Policy: `.github/SECURITY.md`
- Support: `.github/SUPPORT.md`
- Code of Conduct: `.github/CODE_OF_CONDUCT.md`
- Changelog: `CHANGELOG.md`
