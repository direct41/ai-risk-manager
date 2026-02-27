# Changelog

All notable changes to this project are documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [Unreleased]

### Added
- Trust-first eval gates with in-repo thresholds (`eval/trust_thresholds.json`) and CI enforcement in weekly eval workflow.
- Eval trend tracking artifacts:
  - `eval/results/trust_gate.json`
  - `eval/results/trust_history.jsonl`
  - `eval/results/trust_trend.json`
  - `eval/results/trust_trend.md`
- Support-level x CI-mode compatibility matrix with machine-readable `effective_ci_mode` in run summary and API response summary.
- Dependency policy profiles (`conservative|balanced|aggressive`) and scope-aware dependency severity (`runtime` vs `development`).
- Evidence/confidence-aware ranking in reports and PR summary output.

### Changed
- `block-new-critical` guardrails now trigger only for `new + critical + high confidence + verified evidence` findings.
- Transition invariant rule reduced false positives via declared transition anchors.
- PR-focused summary behavior and reporting metadata improved for trust-first rollout.
- Backlog artifacts updated to mark all P0 trust-first epics done.

### Fixed
- Pipeline/report consistency: `effective_ci_mode` and CI/fail notes are now computed before markdown artifact generation.
- Semantic AI payload validation now rejects unsupported severity/confidence labels and degrades gracefully.
- Collector noise reduction: scanning skips `eval/`, `fixtures/`, and `testdata/` directories.

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
