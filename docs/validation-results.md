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

## Validation Sprint 4 - 2026-06-14

This sprint reviewed empty, null, missing, and default-value behavior at form, serializer, renderer, pagination, and request-factory boundaries.

| Case | Decision | Top finding | False positive | Missed risk | Reviewer/test impact |
|---|---|---|---|---|---|
| [FastAPI #12134](https://github.com/fastapi/fastapi/pull/12134) | `ready` | none | none | optional form value re-insertion regression | Add empty-string coverage for optional form fields with a `None` default before merging raw form completion logic. |
| [FastAPI #13537](https://github.com/fastapi/fastapi/pull/13537) | `ready` | none | none after boundary-test fix | none | No change; urlencoded and multipart tests reproduce the confirmed regression. |
| [DRF #7718](https://github.com/encode/django-rest-framework/pull/7718) | `ready` | none | none | empty-to-null conversion with min/max validators | Combine new empty/null conversion behavior with configured validators. |
| [DRF #8067](https://github.com/encode/django-rest-framework/pull/8067) | `ready` | none | none | none | No change; constrained DecimalField empty values are covered directly. |
| [DRF #3731](https://github.com/encode/django-rest-framework/pull/3731) | `ready` | none | none | none | No change; empty temporal-field representation is covered. |
| [DRF #3677](https://github.com/encode/django-rest-framework/pull/3677) | `ready` | none | none | none | No change; nested empty-value rendering is covered. |
| [DRF #4260](https://github.com/encode/django-rest-framework/pull/4260) | `ready` | none | none | none | No change; empty pagination query values are preserved by focused tests. |
| [DRF #5351](https://github.com/encode/django-rest-framework/pull/5351) | `ready` | none | none after boundary-test fix | none | No change; empty-body content-type metadata is covered directly. |

Sprint result:

- 8 isolated public runs completed.
- 6 fix/control PRs remain clean.
- 2 confirmed false negatives were reproduced, but their mechanisms differ:
  - raw form values reinserted after optional/default normalization;
  - empty-to-null conversion interacting with field validators.
- No broad boundary rule was promoted because there is not yet a second independent confirmed regression in either mechanism family.
- Focused positive boundary regression tests named for empty, blank, null, default, or content-type behavior no longer receive unrelated missing-negative-path findings.
- Historical PRs remain reproducible when their old base branch name has been deleted because checkout now fetches the exact public base SHA.

## Sprint 4 Improvements

| Priority | Improvement | Evidence | Acceptance criterion | Status |
|---|---|---|---|---|
| P0 | Reproduce historical PRs after base branch deletion. | Older DRF PRs referenced `master`, which no longer exists as a remote branch even though the exact base SHA remains public. | `review-pr` fetches the exact base SHA without requiring the historical branch ref. | completed |
| P0 | Avoid negative-path noise on positive boundary regression tests. | FastAPI #13537 and DRF #5351 test successful empty/default compatibility, not endpoint failure semantics. | Explicit empty/null/missing/default/content-type regression tests remain `ready` without suppressing ordinary write-path checks. | completed |
| P1 | Preserve evidence gates for new boundary rules. | FastAPI #12134 and DRF #7718 are real misses with different mechanisms. | Both are executable `missed_risk` corpus cases, and no unsupported general rule is introduced. | completed |

## Next Validation Gate

Find a second independent confirmed regression matching either raw-value re-insertion after normalization or empty-to-null conversion with validators. Promote only that repeated mechanism, with the current fix PRs as clean controls.

## Targeted UI Smoke Validation - 2026-06-15

Three changed journeys were validated across a vanilla Express `public/` shell and a Nuxt app-dir frontend.

| Layout | Changed journey | Result | Runtime and setup |
|---|---|---|---|
| Express with vanilla `public/` shell | `app_shell` | Passed login and note creation in Chromium | About 5 seconds after the existing local server started |
| Nuxt app-dir route | `checkout` | Failed because the local commerce backend on port `9000` was unavailable | About 4 seconds; frontend dependencies were already installed |
| Nuxt app-dir shared component | `cart/cartdrawer` | Passed Nuxt shell launch after the selection fix; initially no command ran | About 3 seconds |

The component pilot exposed a correctness defect: component targets appeared in review focus but only route journeys reached the declared smoke runner. Route and component journeys now use the same opt-in selection path, with the changed component retained as failure evidence.

Command behavior was verified end to end:

- without `AIRISK_UI_SMOKE_ENABLE_COMMANDS=1`, mapped commands are reported as skipped and are not executed
- successful commands add a journey-specific note without a finding
- non-zero commands produce `ui_journey_smoke_failed` with the changed UI file, manifest, command, exit code, and output excerpt

No false-positive journey selection was observed. One component-only journey was missed before the fix. Real browser checks require a separately managed application server, and framework journeys may depend on backend services and seeded state outside the frontend package.

Decision: keep targeted declared smoke execution opt-in and limited to changed journeys. Do not add screenshot diffing, whole-site snapshots, automatic dev-server lifecycle management, or a cross-browser matrix until repositories repeatedly adopt stable journey commands in their own browser-test setup.

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
