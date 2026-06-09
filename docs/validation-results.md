# Validation Results Template

Use this file as the public template for tracking external validation runs. Keep the actual working log private until every row is reviewed for privacy and attribution.

Do not record secrets, private repository names, customer names, private vulnerability details, personal contact data, or non-public business context.

## Current Validation Goal

Prove whether engineers, tech leads, and QA reviewers get practical value from a deterministic test-first merge-risk summary for public backend PRs.

Target command:

```bash
riskmap review-pr https://github.com/OWNER/REPO/pull/123
```

## Result Row Template

| Field | Value |
|---|---|
| Date | YYYY-MM-DD |
| PR URL | `https://github.com/org/repo/pull/123` |
| Stack | FastAPI / Django/DRF / Express / other |
| Reviewer role | backend engineer / tech lead / QA / maintainer |
| Command | `riskmap review-pr ...` |
| Exit code | 0 / 1 / 2 / 3 |
| Merge decision | `ready` / `review_required` / `block_recommended` |
| Useful? | yes / mixed / no |
| Most useful output | short note |
| Top false positive | short note |
| Missed risk | short note |
| Setup blocker | none / install / clone / unsupported stack / other |
| Requested workflow | local CLI / GitHub Action / PR comment / hosted / none |
| Follow-up | issue / PR / docs / no action |

## Weekly Summary Template

| Metric | Count |
|---|---:|
| Public PRs reviewed | 0 |
| People who requested or ran analysis | 0 |
| Useful results | 0 |
| Mixed results | 0 |
| Not useful results | 0 |
| Repeat/CI/PR-comment requests | 0 |
| Setup failures | 0 |

## Decision Rule

Continue investing when external runs show that the output changes what a reviewer would inspect or test before merge.

Prioritize distribution and workflow only after the test-first output is repeatedly useful. Prioritize scoring and wording if the output is understood but too obvious or noisy. Pause stack expansion unless the same unsupported stack appears in repeated useful validation requests.
