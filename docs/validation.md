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

For repeatable validation across known public PRs, run the corpus benchmark:

```bash
riskmap benchmark-prs eval/public_prs.json --output-dir .riskmap/public-pr-corpus
cat .riskmap/public-pr-corpus/benchmark_summary.md
```

`eval/public_prs.json` is a labeled regression corpus, not an independent holdout set. The synthetic repositories under `eval/repos/` are tuning and regression fixtures. The project does not currently claim statistical generalization: release claims that require an independent benchmark remain blocked until a separately sourced, frozen holdout corpus is established.

The lifecycle and isolation requirements for that future corpus are defined in `docs/holdout-protocol.md`, prepared with `scripts/holdout_workflow.py`, and enforced by `scripts/check_eval_isolation.py`.

The synthetic eval suite reports `forbidden-rule avoidance` and `required-rule recall`. These are deterministic fixture-contract checks, not statistical precision and recall measured on an independently sampled population.

Critical decision modules (`rules/policy.py`, `trust/scoring.py`, `triage/merge.py`, and `pr_scope.py`) have a pinned mutation gate. Run `make mutation`; CI requires at least 75% killed mutants and rejects untested, suspicious, timed-out, interrupted, or crashed mutants. The 2026-06-22 baseline is 674/875 killed (77.03%), with zero invalid run statuses.

The deterministic analyzer has cold-process latency and peak-memory SLOs for 50-, 250-, and 1,000-file synthetic repositories. Run `make performance`; CI executes three repetitions per workload, enforces [the versioned budgets](../performance/slo.json), and uploads the full JSON result. See [the performance baseline and measurement contract](performance.md).

The benchmark records two verdict layers per PR: execution status (`pass`, `setup_fail`, `provider_fail`, `tool_fail`, `artifact_fail`, or `timeout`) and product evaluation (`passed`, `failed`, or `needs_human_review`). Treat `needs_human_review` rows as labeling work, not as product success.

Inspect the labeling queue and validate corpus metadata:

```bash
riskmap corpus-status eval/public_prs.json --strict
cat .riskmap/public-pr-corpus-status/corpus_status.md
```

Label a reviewed case by changing `expected.product` and adding:

```json
"head_sha": "<reviewed-40-character-commit-sha>",
"label": {
  "outcome": "good_signal",
  "rationale": "The report surfaced the changed-file risk and proposed the right regression test.",
  "reviewed_at": "2026-06-10"
}
```

Use `good_signal`, `noisy`, `false_positive`, or `missed_risk`. Pending cases keep `product=needs_human_review` and omit `label`. Every labeled case records the exact PR head SHA that was reviewed. A later benchmark run fails with an explicit head-drift error when an open PR changes, so maintainers can review the new diff instead of treating stale expectations as a product regression. The strict gate allows pending cases but rejects resolved products without label metadata, labeled cases without a reviewed head SHA, labels attached to pending products, and inconsistent outcome/product pairs.

## Independent Judge

Use an external model as a blind second opinion, not as part of the product analysis. Generate benchmark artifacts first, then run only explicitly selected pending cases:

```bash
riskmap judge-prs eval/public_prs.json \
  --benchmark-dir .riskmap/public-pr-corpus \
  --output-dir .riskmap/external-judge \
  --case-id fastapi-15676 \
  --judge claude \
  --model claude-sonnet-4-6 \
  --max-budget-usd 1
```

This optional workflow requires an installed and authenticated Claude Code CLI. The model is invoked non-interactively with tools disabled, no session persistence, an explicit timeout, and a per-case budget.

Run Gemini against the same packets as a second model family:

```bash
riskmap judge-prs eval/public_prs.json \
  --benchmark-dir .riskmap/public-pr-corpus \
  --output-dir .riskmap/external-judge \
  --case-id fastapi-15676 \
  --judge gemini \
  --model gemini-2.5-pro
```

Gemini runs with temporary system settings that disable MCP, extensions, and skills. Its only declared core tool is administratively set to `ask_user`, which Gemini CLI treats as `deny` in non-interactive mode. Gemini CLI OAuth availability depends on the Google account region. If OAuth is unavailable, configure `GEMINI_API_KEY` through Google AI Studio where supported. A Gemini web subscription alone does not guarantee CLI/API access.

The workflow:

1. Fetches public PR metadata and file patches from GitHub.
2. Builds a packet without corpus reasons, expectations, or existing labels.
3. Gives the selected judge no tools or repository access and treats PR text as untrusted data.
4. Requires the benchmark's recorded PR head SHA to match the current GitHub head.
5. Stores the raw response and a validated assessment separately.
6. Pins the assessment to a SHA-256 packet hash so stale reviews cannot join consensus.

The command requires at least one `--case-id`; use `--all-pending` only for an intentional full batch. Generated evidence and model responses remain under ignored `.riskmap/`.

To compare assessments, place another normalized assessment under:

```text
.riskmap/external-judge/<case-id>/assessments/<judge-name>.json
```

Use the current packet's `case_id` and `packet_hash`:

```json
{
  "schema_version": "1.0",
  "case_id": "fastapi-15676",
  "packet_hash": "<sha256-from-packet.json>",
  "judge": "human-reviewer",
  "model": "human",
  "outcome": "noisy",
  "confidence": "high",
  "correct_signals": [],
  "false_positives": [],
  "missed_risks": [],
  "rationale": "Concise evidence-based explanation.",
  "generated_at_utc": "2026-06-10T00:00:00Z"
}
```

Then run:

```bash
riskmap judge-consensus .riskmap/external-judge
cat .riskmap/external-judge/consensus.md
```

Consensus requires at least two distinct judges with matching `case_id`, `packet_hash`, and outcome. Disagreement, stale assessments, and single-judge results stay in human review. Consensus never edits `eval/public_prs.json`; a maintainer must inspect the evidence and commit the final label separately.

`judge-consensus` returns exit code `3` until every case has valid matching assessments from at least two judges.

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
| Top three findings or actions | exact short labels from the report |
| Review/test impact | yes / partly / no, with one concrete behavior change |
| Useful? | yes / mixed / no |
| Top false positive | short note |
| Missed risk | short note |
| Setup friction | none / install / clone / timeout / unsupported stack / artifact |
| Next requested workflow | local CLI / GitHub Action / PR comment / none |
| Run again? | yes / maybe / no |

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
