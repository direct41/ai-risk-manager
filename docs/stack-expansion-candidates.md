# Stack Expansion Candidates (Stage 7)

This document captures the next stack candidates selected for contract-driven expansion.

## Selection Criteria

- Contract fit (`plugin_contract v1`): expected ability to map required `l1/l2` capabilities.
- Risk coverage gain: expected improvement in practical backend risk scenarios.
- Extraction feasibility: complexity of endpoint/test/dependency extraction.
- Eval feasibility: ability to build compact parity repos with deterministic assertions.

Scoring scale: `1` (low) .. `5` (high).

## Candidate Matrix

| Candidate stack id | Contract fit | Risk coverage gain | Extraction feasibility | Eval feasibility | Total |
|---|---:|---:|---:|---:|---:|
| `flask_pytest` | 5 | 5 | 5 | 5 | 20 |
| `starlette_pytest` | 4 | 3 | 4 | 4 | 15 |
| `aiohttp_pytest` | 3 | 3 | 3 | 3 | 12 |

## Decision

Primary next candidate:

- `flask_pytest` (highest total score, closest fit to current risk model, fastest parity rollout)

Secondary candidate:

- `starlette_pytest` (strong contract compatibility and manageable extraction path)

Deferred candidate:

- `aiohttp_pytest` (lower short-term ROI, can follow after Flask parity stabilization)

## Stage-7 Execution Impact

- Parity eval suites should be implemented first for `flask_pytest`.
- Support-level promotion gate should remain conservative until Flask parity cases and trust gates are stable.
