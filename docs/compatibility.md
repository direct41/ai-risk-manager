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

## JSON artifact compatibility

Artifacts include metadata fields:

- `schema_version`
- `generated_at`
- `tool_version`

Breaking changes include:

- removing required top-level fields (`nodes`, `findings`, `items`)
- changing field meanings or types without major release

Additive fields are allowed in minor releases.
