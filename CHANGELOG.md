# Changelog

All notable changes to this project are documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [Unreleased]

### Added
- Added 10 evidence-backed public PR cases from FastAPI, Django REST framework, Express, and the full-stack FastAPI template, including reviewer-impact notes and a confirmed compatibility false negative.
- Added a PR diff signal for query parser `arrayLimit` changes without indexed-bracket compatibility coverage.
- Added 8 parser and serialization validation cases, including the confirmed DRF empty-datetime renderer regression and seven clean controls.
- Added a narrow PR diff signal for strict datetime parsing of field-derived values without empty-string or null regression coverage.
- Added 8 boundary and optional-value validation cases covering form extraction, serializer conversion, rendering, pagination, and empty request bodies.

### Changed
- Deterministic test plans now use dependency and regression-specific assertions for generic PR delta findings instead of API response boilerplate.
- Public PR validation now uses the historical base commit reported by GitHub for reproducible merged-PR baselines and diffs.
- Positive boundary regression tests named for empty, blank, null, default, or content-type behavior no longer receive unrelated missing-negative-path findings.

### Fixed
- Old merged PRs in high-velocity repositories no longer fall back to noisy full-repository analysis when their merge base is outside the shallow branch history.
- Historical PR checkout no longer requires a deleted base branch when GitHub provides the exact public base commit SHA.
- Unchanged baseline findings no longer affect default `review-pr` decisions, risk scores, or test-first actions.

## [0.2.0] - 2026-06-11

### Added
- Added PR diff detection for dynamic Python gettext message identifiers that cannot be extracted reliably.
- Added PR diff detection for newly introduced 4xx branches without matching negative-path test assertions.
- Added PR diff detection for documented mapping-key renames that leave stale public contracts.
- Added a Django integrity signal for shared constant create defaults inside uniqueness handling.
- Added a Python integrity signal for lossy `decode(errors="replace"|"ignore")` transformations.
- Added Gemini CLI as a second external-judge adapter with the same blind packet and consensus contracts as Claude.
- Added a blind external-judge workflow with GitHub PR evidence packets, pinned Claude assessments, packet-hash provenance, and multi-judge consensus reporting.
- Public PR reviews now write head-SHA metadata so downstream validation cannot combine stale reports with newer PR patches.
- Added `riskmap corpus-status` with a human-review queue, label outcome metrics, and a strict corpus metadata gate.
- Added `riskmap benchmark-prs` with a public PR corpus runner, machine summary, and human-readable benchmark report for repeatable real-PR validation.
- Added a public PR review request issue template and validation-results template to make external alpha feedback easier to collect.
- Added `riskmap review-pr <github-pr-url>` to run deterministic PR risk triage on a public GitHub PR without manually checking out the branch, including automatic base-branch baseline generation.
- Added a public validation playbook for the 30-day product-value test cycle.
- Added a CI public-artifact gate and PR release-manager checklist to prevent accidental publication of local notes, generated outputs, secrets, or unreviewed public docs.
- Added a GitLab CI merge-request review example for advisory risk analysis.

### Changed
- Exact source-only `trimRight` to `trimEnd` and `trimLeft` to `trimStart` rewrites no longer trigger a disproportionate generic missing-test reminder when `package.json` proves Node 10+ compatibility; mixed changes or unknown runtimes remain review-required.
- Public PR corpus manual review is complete with all 23 cases carrying evidence-backed product outcomes.
- Public PR corpus now includes independent controls for exact JavaScript alias rewrites, mixed host-extraction changes, and dynamic gettext messages.
- Public PR corpus now includes verified UI interaction, startup diagnostics, and Django header-compatibility outcomes.
- Public PR corpus now includes verified DRF compatibility, uniqueness, and clean-control outcomes from retrospective review.
- Generated-test analysis now focuses on the test's primary write call, avoids treating captured current time as standalone flakiness evidence, and keeps unchanged generated-test debt out of PR merge actions.
- Public PR benchmark seed corpus now includes 15 additional unlabeled candidates from FastAPI, DRF, Express, and full-stack FastAPI template repositories.
- Public PR benchmark seed corpus now labels all initial public PR cases with expected product outcomes.
- Alpha feedback prompts now lead with public PR URL validation and safer output-snippet guidance.
- README now leads with the one-command public GitHub PR review path and feedback prompts tied to real PR URLs.
- README now has a clearer public first screen with badges, problem framing, capability summary, quick paths, and a concise "How it works" section for human and AI discovery.
- Public documentation was narrowed to user, operator, and contributor references; maintainer-only roadmap, release checklist, UI pilot notes, and launch kit are now local ignored files.
- Root-level public documents were reduced to README, changelog, and license files; GitHub community docs now live under `.github/`.
- Alpha onboarding was consolidated into README feedback guidance; `ALPHA.md` is now a local ignored maintainer note.
- Source distributions now explicitly exclude repository-only docs, eval fixtures, tests, examples, scripts, and local maintainer notes.
- Package license metadata now uses SPDX-style `MIT` metadata with explicit license-file declaration.

### Removed
- Removed stale `docs/legacy-review.md` from the repository.
- Removed the empty root `.gitkeep` placeholder.

### Fixed
- PR comment delivery failures no longer mark an otherwise successful AI Risk Analysis workflow as failed.
- Kept Gemini external-judge tool isolation compatible with Gemini CLI 0.46.0.
- Full-fallback PR summaries now hide unscoped new high-severity repo-wide findings from top risks and test-first actions.
- PR summaries now stay aligned with merge triage test-first actions, and full-fallback PR analysis hides repo-wide unchanged noise from merge triage scoring.
- GitHub Actions example now installs from the GitHub repository while the package is not published on PyPI.

## [0.1.1] - 2026-04-21

### Added
- Dependabot configuration for Python dependencies and GitHub Actions.
- Alpha feedback issue template for public alpha onboarding.
- Public alpha onboarding prompts and local usage steps.
- Profile-based architecture and roadmap documentation for `code_risk`, `ui_flow_risk`, and `business_invariant_risk`.
- Trust-first eval gates with in-repo thresholds (`eval/trust_thresholds.json`) and CI enforcement in weekly eval workflow.
- Eval trend tracking outputs generated under ignored `eval/results/`:
  - `eval/results/trust_gate.json`
  - `eval/results/trust_history.jsonl`
  - `eval/results/trust_trend.json`
  - `eval/results/trust_trend.md`
- Support-level x CI-mode compatibility matrix with machine-readable `effective_ci_mode` in run summary and API response summary.
- Dependency policy profiles (`conservative|balanced|aggressive`) and scope-aware dependency severity (`runtime` vs `development`).
- Evidence/confidence-aware ranking in reports and PR summary output.
- Policy externalization via `.airiskpolicy` (JSON) with per-rule `enabled`, `severity`, and `gate` overrides.
- Coverage mapping improvements for route params, local path aliases, and fixture-derived path aliases.
- Added `django_drf` collector plugin with route/test coverage extraction for common APIView/urlpatterns patterns.
- Expanded `django_drf` extraction with DRF router/viewset endpoint mapping and `reverse(...)`-based test path resolution.
- Added Django viewset eval fixture `eval/repos/milestone7_django_viewset` and included it in eval-suite cases.
- Added shared dependency extraction parity for FastAPI and Django plugins, with a Django dependency-policy eval fixture (`eval/repos/milestone8_django_dependency`).
- Added stack expansion readiness artifact `eval/results/expansion_gate.json` driven by consecutive trust-gate passes and required Django parity eval cases.
- Added explicit graph artifacts split:
  - `graph.analysis.json` (analysis graph)
  - `graph.deterministic.json` (deterministic pre-enrichment graph)
- Added run summary metadata for graph transparency:
  - `graph_mode_applied`
  - `semantic_signal_count`
- Added merge-risk triage artifacts:
  - `merge_triage.md`
  - `merge_triage.json`
- Added `ready|review_required|block_recommended` merge decision packaging with a 10-minute test-first order.
- Declared UI smoke examples and explicit business critical-flow documentation for alpha validation.

### Changed
- README and Russian quickstart now prioritize the external self-serve path before deeper architecture details.
- GitHub metadata links, security reporting entrypoint, and CI matrix were hardened for public alpha readiness.
- CLI/API analysis defaults now stay deterministic/no-LLM unless AI enrichment is explicitly requested.
- Declared UI smoke command execution is gated behind `AIRISK_UI_SMOKE_ENABLE_COMMANDS=1`.
- API path access is constrained to approved workspace/output roots for hardened deployments.
- Internal diagnostic and finding fallback hashes now use SHA-256, while PR baseline comparison still recognizes legacy SHA-1 finding fingerprints.
- Local Makefile onboarding now uses the project `.venv` and runs the bundled demo in deterministic/no-LLM mode.
- Development/API dependency pins were updated to Python 3.13-compatible versions.
- `block-new-critical` guardrails now trigger only for `new + critical + high confidence + verified evidence` findings.
- Transition invariant rule reduced false positives via declared transition anchors.
- PR-focused summary behavior and reporting metadata improved for trust-first rollout.
- Backlog artifacts updated to mark all P0 trust-first epics done.
- Exit-code gating (`--fail-on-severity`, `ci_mode`) now respects `.airiskpolicy` per-rule blocking overrides (`gate=never_block`).
- Auto support level for `django_drf` now defaults to `l2` (full CI-mode matrix behavior).
- In `support_level=auto`, preflight warnings now downgrade support level by one step to keep blocking behavior conservative.
- Stack expansion gate criteria are now completion-based (consecutive trust-pass runs) instead of calendar-tied wording.
- README was streamlined for faster onboarding and updated baseline guidance.
- CI risk-analysis baseline now uses deterministic/no-llm mode and caches both `graph.json` and `findings.json` for correct PR delta status.
- PR risk-analysis workflow now separates branch-code analysis from trusted PR comment publication.
- Reports and PR summaries now surface merge triage decision, release-risk score, and top test-first actions.
- Root-level planning docs were removed in favor of `README.md` and focused user/operator docs.

### Fixed
- Packaged the deterministic sample repository so `riskmap analyze --sample` works after a normal wheel/GitHub install, not only from a source checkout.
- No-finding runs now report perfect precision/actionability proxies and zero triage time instead of misleading `0%` quality metrics.
- Pipeline/report consistency: `effective_ci_mode` and CI/fail notes are now computed before markdown artifact generation.
- Semantic AI payload validation now rejects unsupported severity/confidence labels and degrades gracefully.
- Collector noise reduction: scanning skips `eval/`, `fixtures/`, and `testdata/` directories.
- FastAPI and Django collectors now also skip build, dist, and coverage artifacts.
- LLM and GitHub outbound API clients now reject non-HTTP(S) API base URLs before opening connections.

### Refactored
- Removed unused `risk_agent` layer.
- Unified bundled sample repository resolution for both CLI and API via shared helper (`sample_repo.py`).

## [0.1.0] - 2026-02-19

### Added
- Core `run_pipeline` flow for deterministic analysis + optional LLM enrichment.
- CLI adapter (`riskmap analyze`) with full and PR modes.
- API adapter (`riskmap-api`, `/healthz`, `/v1/analyze`) over the same pipeline.
- FastAPI extractor plugin with stack detection and collector plugin registry.
- Rule engine findings + report/test plan artifacts.
- CI workflows for quality gates, risk analysis, and weekly eval suite.
