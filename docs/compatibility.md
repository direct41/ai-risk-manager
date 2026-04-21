# Compatibility Policy

This document describes compatibility of the **current shipped runtime**.

The canonical architecture is now profile-based and capability-aware.
Current stack-plugin and repository-wide support semantics remain supported as compatibility layers during migration.

## Versioning

- Semantic versioning (`MAJOR.MINOR.PATCH`).
- `PATCH`: bug fixes, no contract breaks.
- `MINOR`: additive CLI/JSON changes.
- `MAJOR`: breaking changes.

## CLI compatibility

Breaking changes include:

- removing flags or changing default behavior incompatibly
- changing exit code semantics

## API compatibility

Breaking changes include:

- removing `GET /healthz` or `POST /v1/analyze`
- changing `POST /v1/analyze` response contract fields:
  `exit_code`, `notes`, `output_dir`, `artifacts`, `result`, `summary`
- moving pipeline execution errors from `exit_code` to incompatible HTTP semantics

Additive response fields are allowed in minor releases.
API hardening that rejects unsafe unauthenticated public-host or out-of-root path requests is considered compatible because the endpoint contract stays unchanged for valid requests.

## JSON artifact compatibility

Artifacts include metadata fields:

- `schema_version`
- `generated_at`
- `tool_version`

Additional artifacts (for example `run_metrics.json`, `expansion_gate.json`) may be added in minor releases.
PR-mode helper artifacts such as `pr_summary.json`, `pr_summary.md`, and `github_check.json` are additive and may evolve with new additive fields.
That includes additive profile summary fields and compact trust metadata on top findings.
Optional repo-local config such as `./.riskmap-ui.toml` may add behavior in minor releases without changing the output contract shape; command execution remains gated by environment.
Finding-level additive metadata such as `trust` is allowed in minor releases.

Breaking changes include:

- removing required top-level fields (`nodes`, `findings`, `items`)
- changing field meanings or types without major release

Additive fields are allowed in minor releases.

Repository-wide fields such as `support_level_applied`, `repository_support_state`, `competitive_mode`, and `graph_mode_applied` are still supported today.
They should be treated as compatibility fields while profile-level applicability is introduced.

## Policy file compatibility (`.airiskpolicy`)

- `.airiskpolicy` is an optional JSON config file loaded from repository root.
- Current schema version: `1`.
- Additive rule fields are allowed in minor releases.

Breaking changes include:

- changing meaning of existing fields (`enabled`, `severity`, `gate`)
- removing version `1` support without a major release

## Plugin contract compatibility

`plugin_contract v1` is still supported for the current `code_risk` profile.
It is no longer the canonical product architecture and should be treated as a compatibility surface, not as the preferred expansion model for future risk profiles.

- Collector plugin contract current version: `1`.
- Contract governs plugin capability declaration and conformance gates.
- New plugins must declare:
  - `plugin_contract_version`
  - `target_support_level`
  - `supported_signal_kinds`
  - `unsupported_signal_kinds`

Breaking changes include:

- changing support-level required capabilities (`l0/l1/l2`) incompatibly
- changing semantics of existing signal kinds in the contract
- removing support for contract version `1` without a major release

## Future additive compatibility

Profile-aware applicability is expected to arrive as an additive contract.
Planned states per profile:

- `supported`
- `partial`
- `not_applicable`

This should be additive to the existing repository-wide compatibility surface before any repository-wide fields are retired.
