# Compatibility Policy

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
Enabling optional API auth via `AIRISK_API_TOKEN` is considered additive hardening; endpoint contracts stay unchanged.

## JSON artifact compatibility

Artifacts include metadata fields:

- `schema_version`
- `generated_at`
- `tool_version`

Additional artifacts (for example `run_metrics.json`, `expansion_gate.json`) may be added in minor releases.

Breaking changes include:

- removing required top-level fields (`nodes`, `findings`, `items`)
- changing field meanings or types without major release

Additive fields are allowed in minor releases.

## Policy file compatibility (`.airiskpolicy`)

- `.airiskpolicy` is an optional JSON config file loaded from repository root.
- Current schema version: `1`.
- Additive rule fields are allowed in minor releases.

Breaking changes include:

- changing meaning of existing fields (`enabled`, `severity`, `gate`)
- removing version `1` support without a major release

## Plugin contract compatibility

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
