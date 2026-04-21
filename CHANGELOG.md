# Changelog

All notable changes to this project are documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [Unreleased]

## [0.1.1] - 2026-04-21

### Added
- Dependabot configuration for Python dependencies and GitHub Actions.
- Product Hunt launch kit and alpha feedback issue template for public alpha onboarding.
- Alpha testing guide (`ALPHA.md`) with local usage steps, feedback prompts, and LinkedIn-ready positioning text.
- Profile-based architecture and roadmap documentation for `code_risk`, `ui_flow_risk`, and `business_invariant_risk`.
- Trust-first eval gates with in-repo thresholds (`eval/trust_thresholds.json`) and CI enforcement in weekly eval workflow.
- Eval trend tracking artifacts:
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
- Reports and PR summaries now surface merge triage decision, release-risk score, and top test-first actions.
- Root-level planning docs were removed in favor of `README.md`, `ALPHA.md`, and `docs/roadmap.md`.

### Fixed
- Packaged the deterministic sample repository so `riskmap analyze --sample` works after a normal wheel/GitHub install, not only from a source checkout.
- No-finding runs now report perfect precision/actionability proxies and zero triage time instead of misleading `0%` quality metrics.
- Pipeline/report consistency: `effective_ci_mode` and CI/fail notes are now computed before markdown artifact generation.
- Semantic AI payload validation now rejects unsupported severity/confidence labels and degrades gracefully.
- Collector noise reduction: scanning skips `eval/`, `fixtures/`, and `testdata/` directories.

### Refactored
- Removed unused `risk_agent` layer.
- Unified bundled sample repository resolution for both CLI and API via shared helper (`sample_repo.py`).
- Extracted PR scope and baseline helper logic from `pipeline/run.py` into `pipeline/pr_scope.py` to reduce orchestrator complexity.

## [0.1.0] - 2026-02-19

### Added
- Core `run_pipeline` flow for deterministic analysis + optional LLM enrichment.
- CLI adapter (`riskmap analyze`) with full and PR modes.
- API adapter (`riskmap-api`, `/healthz`, `/v1/analyze`) over the same pipeline.
- FastAPI extractor plugin with stack detection and collector plugin registry.
- Rule engine findings + report/test plan artifacts.
- CI workflows for quality gates, risk analysis, and weekly eval suite.
