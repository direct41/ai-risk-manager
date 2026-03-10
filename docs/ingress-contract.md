# Ingress Contract v1

This document defines the normalized ingress contract introduced in Stage 13.

## Purpose

- stop treating HTTP endpoints as the only first-class system entrypoint
- give plugins one shared contract for sink families
- allow capability packs to attach to ingress families instead of framework-specific shapes

## Supported Families In v1

- `http`
- `webhook`
- `job`
- `cli_task`
- `event_consumer`

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
- `queue.process(...)`, `worker.process(...)`, `agenda.define(...)` are classified as `job`
- `program.command(...)`, `cli.command(...)`, `yargs.command(...)` are classified as `cli_task`
- `bus.on(...)`, `consumer.subscribe(...)`, `subscriber.on(...)` are classified as `event_consumer`
- any detected test HTTP call becomes `test_to_ingress_coverage`
- `runJob(...)` and `runCli(...)` in tests are mapped to ingress coverage heuristics
- `emitEvent(...)` in tests is mapped to `event_consumer` coverage heuristics

## Current Eval Coverage

- `milestone15_fastapi_webhook_ingress` verifies that a non-HTTP-style sink family represented over HTTP transport is classified as `webhook`
- the eval suite also verifies webhook test coverage through `test_to_ingress_coverage`
- `milestone16_express_job_cli_ingress` verifies `job` and `cli_task` families plus their coverage heuristics
- `milestone17_express_event_consumer_ingress` verifies `event_consumer` family plus its coverage heuristic

## Non-Goals

- no new deterministic rules are attached to ingress families in v1
- graph topology remains backward-compatible with the existing HTTP-centric runtime
- plugin contract support levels remain anchored to current HTTP rules until ingress-based rules are introduced
