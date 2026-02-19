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
  `exit_code`, `notes`, `output_dir`, `artifacts`, `result`
- moving pipeline execution errors from `exit_code` to incompatible HTTP semantics

## JSON artifact compatibility

Artifacts include metadata fields:

- `schema_version`
- `generated_at`
- `tool_version`

Breaking changes include:

- removing required top-level fields (`nodes`, `findings`, `items`)
- changing field meanings or types without major release

Additive fields are allowed in minor releases.
