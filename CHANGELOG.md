# Changelog

All notable changes to this project are documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [Unreleased]

### Changed
- OSS documentation and governance polish (`README`, `SECURITY`, `SUPPORT`, release/process docs).

## [0.1.0] - 2026-02-19

### Added
- Core `run_pipeline` flow for deterministic analysis + optional LLM enrichment.
- CLI adapter (`riskmap analyze`) with full and PR modes.
- API adapter (`riskmap-api`, `/healthz`, `/v1/analyze`) over the same pipeline.
- FastAPI extractor plugin with stack detection and collector plugin registry.
- Rule engine findings + report/test plan artifacts.
- CI workflows for quality gates, risk analysis, and weekly eval suite.
