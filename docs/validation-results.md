# Validation Results Template

Use this file as the public template for tracking external validation runs. Keep the actual working log private until every row is reviewed for privacy and attribution.

Do not record secrets, private repository names, customer names, private vulnerability details, personal contact data, or non-public business context.

## Current Validation Goal

Prove whether engineers, tech leads, and QA reviewers get practical value from a deterministic test-first merge-risk summary for public backend PRs.

Target command:

```bash
riskmap review-pr https://github.com/OWNER/REPO/pull/123
```

## Validation Sprint 2 - 2026-06-11

All runs used deterministic, no-LLM `riskmap review-pr` analysis in isolated temporary checkouts. Evidence came only from public diffs, tests, issue links, and review threads.

| Case | Decision | Top finding | False positive | Missed risk | Reviewer/test impact |
|---|---|---|---|---|---|
| [FastAPI #15038](https://github.com/fastapi/fastapi/pull/15038) | `review_required` | `pr_code_change_without_test_delta` | none | none | Add a focused TaskGroup cancellation and async exit-stack cleanup regression test. |
| [FastAPI #14786](https://github.com/fastapi/fastapi/pull/14786) | `ready` | none | none | none | No change; focused Authorization whitespace tests cover the changed contract. |
| [FastAPI #13786](https://github.com/fastapi/fastapi/pull/13786) | `ready` | none | none | none | No change; broad scheme tests and compatibility docs cover the 401 contract migration. |
| [DRF #9902](https://github.com/encode/django-rest-framework/pull/9902) | `ready` | none | none | none | No change; final tests cover indexed, non-indexed, partial, and ordering behavior. |
| [DRF #9928](https://github.com/encode/django-rest-framework/pull/9928) | `ready` | none | none | none | No change; the empty-datetime crash has a focused renderer regression test. |
| [DRF #9929](https://github.com/encode/django-rest-framework/pull/9929) | `ready` | none | none | none | No change; the non-editable choices mapping is covered directly. |
| [Express #7181](https://github.com/expressjs/express/pull/7181) | `review_required` | `pr_query_array_limit_without_indexed_compat_test` | none | none after compatibility-rule fix | Test indexed keys below, at, and above the old and new limits and assert object/array shape. |
| [Express #7057](https://github.com/expressjs/express/pull/7057) | `review_required` | `pr_dependency_change_without_test_delta` | none after unchanged-finding fix | none | Verify resolved `qs` version, run the package audit, then execute query-parser compatibility tests. |
| [Full-stack FastAPI #1396](https://github.com/fastapi/full-stack-fastapi-template/pull/1396) | `ready` | none | none | none | No change; separate superuser 404 and regular-user 403 tests preserve the auth boundary. |
| [Full-stack FastAPI #1940](https://github.com/fastapi/full-stack-fastapi-template/pull/1940) | `review_required` | `pr_code_change_without_test_delta` | none | none | Add a settings startup test for a display-name sender plus valid sender-address validation. |

Initial sprint result:

- 10 isolated public runs completed.
- 9 useful outcomes and 1 mixed outcome.
- 0 remaining false positives in top findings.
- 1 confirmed false negative: Express indexed-query compatibility.

Post-improvement result:

- 10 useful outcomes and 0 mixed or not-useful outcomes.
- 0 open false positives and 0 open false negatives in this sprint.
- Express #7181 now returns `review_required`, risk score `46`, and one focused compatibility action.
- Repeated checkout noise was fixed by using each PR's historical public base SHA.
- Unchanged baseline findings no longer affect default PR decision, score, or actions.
- Next workflow decision: keep deterministic `review-pr` as the default advisory path and prioritize diff-level compatibility heuristics over stack expansion.

## Required Improvements

| Priority | Improvement | Evidence | Acceptance criterion | Status |
|---|---|---|---|---|
| P0 | Reproduce merged PRs from their historical base commit. | Older FastAPI PRs lost changed-file scope outside shallow default-branch history. | Historical merged PR resolves its exact changed files without unrelated repository findings. | completed |
| P0 | Keep unchanged baseline findings out of default PR decisions. | Express #7057 initially inherited unrelated dependency-policy actions. | `only_new` excludes unchanged findings from decision, score, and test-first actions while retaining them in audit artifacts. | completed |
| P0 | Detect query-parser array-limit compatibility gaps. | Express #7181 changed indexed-key object/array behavior while only testing repeated keys. | An `arrayLimit` diff without indexed-bracket tests produces one focused `review_required` finding. | completed |
| P1 | Make deterministic test guidance match the changed artifact. | Dependency and internal-code findings previously received generic API response assertions. | Dependency changes request resolver/audit/integration checks; source deltas request focused regression coverage. | completed |
| P1 | Keep the public corpus executable as a regression contract. | Validation conclusions must survive future rule and scoring changes. | All 33 cases are labeled, strict corpus validation passes, and sprint-2 benchmark expectations are machine checked. | completed |

## Deferred By Evidence

- Do not ingest maintainer review comments into normal product analysis yet. Public comments were used to label the corpus, but runtime dependence on review text would weaken deterministic isolation and reproducibility.
- Do not add broad query-parser option scanning yet. Extend beyond `arrayLimit` only after another confirmed case demonstrates a repeated option family such as `allowSparse`, `parseArrays`, or `comma`.
- Do not expand stack support from this sprint. All confirmed cases were in already supported stacks; the remaining defect was diff semantics, not stack extraction.

## Validation Sprint 3 - 2026-06-13

This sprint reviewed parser, renderer, serializer, and compatibility changes with public regression or maintainer evidence.

| Case | Decision | Top finding | False positive | Missed risk | Reviewer/test impact |
|---|---|---|---|---|---|
| [DRF #9365](https://github.com/encode/django-rest-framework/pull/9365) | `review_required` | `pr_strict_field_datetime_parse_without_empty_test` | none | none after empty-value rule | Add empty-string and `None` rendering cases before introducing strict datetime parsing. |
| [DRF #9735](https://github.com/encode/django-rest-framework/pull/9735) | `ready` | none | none | none | No change; ordering, deduplication, nested serialization, and JSON compatibility are covered. |
| [DRF #9973](https://github.com/encode/django-rest-framework/pull/9973) | `ready` | none | none | none | No change; empty and non-empty unhashable values cover the BooleanField fallback. |
| [DRF #9775](https://github.com/encode/django-rest-framework/pull/9775) | `ready` | none | none | none | No change; field mapping, bounds, settings, and string coercion are covered. |
| [FastAPI #12935](https://github.com/fastapi/fastapi/pull/12935) | `ready` | none | none | none | No change; Decimal `NaN` and Infinity crash variants have focused tests. |
| [FastAPI #13207](https://github.com/fastapi/fastapi/pull/13207) | `ready` | none | none | none | No change; computed-field schema behavior is covered in the affected mode. |
| [FastAPI #4972](https://github.com/fastapi/fastapi/pull/4972) | `ready` | none | none | none | No change; repeated encoding proves model configuration is not mutated. |
| [Express #6088](https://github.com/expressjs/express/pull/6088) | `ready` | none | none | none | No change; single, variadic, and comma-delimited charset inputs are covered. |

Sprint result:

- 8 isolated public runs completed.
- 7 clean parser/serialization controls remained `ready`.
- 1 confirmed false negative reproduced: DRF #9365 later crashed on empty datetime values despite broad valid-value coverage.
- The promoted rule is limited to newly added strict datetime parsing of form, field, parser, renderer, or serializer values without an empty-value regression test.
- DRF #9365 now returns `review_required`, risk score `46`, and one focused integration action.
- DRF #9928 remains the real-world clean control for the guarded empty-value fix.

## Sprint 3 Improvement

| Priority | Improvement | Evidence | Acceptance criterion | Status |
|---|---|---|---|---|
| P0 | Detect strict datetime parsing of optional field values without empty-value coverage. | DRF #9365 introduced `fromisoformat`/`strptime` handling, then DRF #9928 fixed the resulting empty-string and `None` crash. | The original PR produces one focused finding; the guarded fix and unrelated datetime parsing remain clean. | completed |
| P1 | Preserve parser and serializer clean controls. | Seven public PRs changed output shape, coercion, schema generation, encoder state, or argument parsing with focused tests. | All seven remain `ready` with zero top findings. | completed |
| P1 | Keep the public corpus executable after adding the new evidence. | Sprint conclusions must survive future signal and scoring changes. | All 41 cases are labeled and strict corpus validation passes. | completed |

## Next Validation Gate

Review another batch of boundary conversions and optional-value handling. Promote broader parser rules only after a second independent confirmed regression; do not generalize this rule to arbitrary `fromisoformat` or `strptime` calls.

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
