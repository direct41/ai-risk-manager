# Validation Playbook

AI Risk Manager is in open alpha. The next product goal is not broader feature coverage. The next goal is to prove whether teams reviewing risky or AI-generated PRs want a deterministic test-first risk summary before merge.

Use this playbook for a 30-day validation cycle.

## Target User

Prioritize people who already feel PR review risk:

- backend engineers reviewing AI-generated or large PRs
- tech leads who decide whether a PR is safe to merge
- QA engineers who need a focused test plan from a code diff
- maintainers of FastAPI, Django/DRF, or Express/Node services

Do not start with security teams looking for SAST replacement, frontend visual QA teams, or teams that want automatic release approval.

## Core Promise

For a public GitHub PR, AI Risk Manager should answer:

> What should I test before merging this PR?

The first proof path is:

```bash
riskmap review-pr https://github.com/OWNER/REPO/pull/123
cat .riskmap/review-pr-OWNER-REPO-123/merge_triage.md
cat .riskmap/review-pr-OWNER-REPO-123/pr_summary.md
```

The command clones the PR into a temporary checkout, builds a baseline on the base branch, runs deterministic/no-LLM analysis by default, and writes local artifacts. Use `--skip-baseline` only when repository size makes the baseline step impractical; it is faster but noisier.

## Public Request Path

Ask people for one hard public PR, not for a star or a generic opinion.

Primary issue template:

```text
https://github.com/direct41/ai-risk-manager/issues/new?template=pr_review_request.yml
```

Use this path when the person has a public GitHub PR but has not run the tool yet. Use the alpha feedback template only after someone has actual output to discuss.

## Outreach Script

Use a short request. Ask for a PR, not a star.

```text
I am validating an open-source tool that turns a risky or AI-generated PR into a test-first merge-risk summary.

If you have one public backend PR that felt hard to review, send me the URL. I will run the tool and reply with:
- the merge-risk decision
- the top risky changed areas
- the first tests I would run before merge

I am looking for blunt feedback: useful, noisy, obvious, or wrong.
```

## Evaluation Questions

For every PR reviewed, record answers to these questions:

- Did the user understand the output without a walkthrough?
- Did the test-first list mention anything they would actually test?
- Was any recommendation wrong, obvious, or too generic?
- Did the user want this in CI, local CLI, or a PR comment?
- Would they run it again on the next risky PR?

## Minimum Evidence Table

Track one row per external PR.

Use `docs/validation-results.md` as the public-safe template. Keep the working copy private until every row has been checked for secrets, customer names, private repository names, and personal contact data.

| Field | Example |
|---|---|
| PR URL | `https://github.com/org/repo/pull/123` |
| Stack | FastAPI, Django/DRF, Express, unknown |
| User role | backend engineer, tech lead, QA |
| Command | `riskmap review-pr ...` |
| Decision | `ready`, `review_required`, `block_recommended` |
| Useful? | yes / mixed / no |
| Top false positive | short note |
| Missed risk | short note |
| Next requested workflow | local CLI / GitHub Action / PR comment / none |

Do not record secrets, private repository names, customer names, or private vulnerability details.

## Success Criteria

Continue investing if at least two of these are true within 30 days:

- 10 external PRs were reviewed.
- 5 people ran the tool or asked for output on their own PR.
- 3 people said the test-first output changed what they would inspect or test.
- 2 people asked for a repeatable CI or PR-comment workflow.

Pivot if users like the idea but do not run the CLI:

- prioritize GitHub Action and PR-comment setup
- consider hosted analysis only after privacy constraints are explicit

Stop or freeze if:

- fewer than 5 real PRs are reviewed after direct outreach
- users consistently say the output is obvious or not tied to their merge decision
- the strongest demand is generic code review rather than release-risk triage

## Product Changes Allowed During Validation

Allowed:

- reduce setup friction
- improve wording of summaries and test-first actions
- add demo PR examples
- fix high-noise false positives
- improve GitHub Action and PR-comment ergonomics

Avoid:

- adding new stack support before the first 10 external PR reviews
- building dashboards or SaaS workflows
- adding broad AI review features that compete directly with mature code-review tools
- changing the core promise away from test-first merge-risk triage without evidence
