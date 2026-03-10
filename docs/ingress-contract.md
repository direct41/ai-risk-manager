# Ingress Contract v1

This document defines the normalized ingress contract introduced in Stage 13.

## Purpose

- stop treating HTTP endpoints as the only first-class system entrypoint
- give plugins one shared contract for sink families
- allow capability packs to attach to ingress families instead of framework-specific shapes

## Supported Families In v1

- `http`
- `webhook`

Planned families:

- `job`
- `event_consumer`
- `cli_task`

## Contract Shape

`ingress_surface` signal attributes:

- `family`
- `protocol`
- `operation`
- `owner_name`
- `target`
- `method`
- `path`
- `snippet`

`test_to_ingress_coverage` signal attributes:

- `family`
- `protocol`
- `operation`
- `test_name`
- `target`
- `method`
- `path`
- `coverage_mode` (optional fallback marker)
- `snippet`

## Current Mapping Rules

- any write endpoint becomes `ingress_surface`
- default family is `http`
- routes or handlers containing `webhook` or paths under `/webhooks` or `/hooks` are classified as `webhook`
- any detected test HTTP call becomes `test_to_ingress_coverage`

## Non-Goals

- no new deterministic rules are attached to ingress families in v1
- graph topology remains backward-compatible with the existing HTTP-centric runtime
- plugin contract support levels remain anchored to current HTTP rules until ingress-based rules are introduced
