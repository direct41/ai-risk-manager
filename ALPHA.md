# Alpha Guide

AI Risk Manager is in limited open alpha.

Use it when you want a short PR risk review that says:

- what changed areas look risky
- what to test first
- whether the PR looks ready or needs focused review

## Best Fit

- backend-heavy services
- FastAPI, Django/DRF, Express/Node repositories
- teams reviewing AI-generated code
- teams that want advisory CI output before blocking merges
- repositories with critical flows that can be declared in `.riskmap.yml`

## Try It Locally

Start with the bundled sample before running on a private repository:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "git+https://github.com/direct41/ai-risk-manager.git"
riskmap analyze --sample --no-llm --analysis-engine deterministic --output-dir ./.riskmap
cat .riskmap/report.md
cat .riskmap/merge_triage.md
```

Then run on your own repository:

```bash
riskmap analyze \
  --mode full \
  --analysis-engine deterministic \
  --no-llm \
  --output-dir ./.riskmap
```

Read these first:

- `.riskmap/merge_triage.md`
- `.riskmap/report.md`

Run on a PR branch:

```bash
riskmap analyze \
  --mode pr \
  --base main \
  --analysis-engine deterministic \
  --no-llm \
  --only-new \
  --output-dir ./.riskmap
```

## What To Evaluate

- Did the top findings point to real review risk?
- Did the report tell you which test to add first?
- Were any findings noisy, stale, or irrelevant?
- Did the output explain support level and profile applicability clearly?
- Did setup or CLI usage block you?

## Send Feedback

Use the alpha feedback issue template:

```text
https://github.com/direct41/ai-risk-manager/issues/new?template=alpha_feedback.yml
```

Include:

- repository stack and shape
- command you ran
- top 3 findings
- which findings were useful or noisy
- what important risk was missed
- whether setup or wording blocked you

## Current Limits

- It is not a generic SAST replacement.
- It is not a full business-logic verifier.
- `ui_flow_risk` runs repo-declared smoke commands only when `AIRISK_UI_SMOKE_ENABLE_COMMANDS=1` is set for a trusted repository.
- Unknown stacks run in partial/advisory mode.
- Merge triage is advisory unless you explicitly enable stricter CI gates.

## Suggested LinkedIn Positioning

> I am opening a small alpha for AI Risk Manager: a PR-native release-risk assistant that helps teams reviewing fast-moving or AI-generated code answer one practical question: what should we test before merge?
>
> It produces a short PR summary with top risks, trust metadata, and test-first actions. It currently works best on FastAPI, Django/DRF, and Express/Node, with early support for UI flow smoke checks and explicit business critical-flow specs.
>
> I am looking for a few engineers, QA leads, and CTOs who can run it on real PRs and tell me where it is useful, noisy, or missing important risk.
