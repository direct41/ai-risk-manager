# AI Risk Manager

Find risky backend flows and missing tests before merge.

AI Risk Manager scans a backend repository and answers two practical questions:

- Which backend flows look risky right now?
- Which tests should we add first?

It works best on backend-heavy codebases and currently supports FastAPI, Django/DRF, and Express/Node repositories.

## Why AI Risk Manager?

- Focuses on release risk instead of generic code quality noise.
- Prioritizes test actions, not just findings.
- Starts with deterministic analysis; AI is optional.
- Supports PR mode to highlight new vs unchanged risk.
- Reports partial support honestly instead of pretending full coverage.

## Install

```bash
pip install -e '.[dev]'
```

## Quick Start

Run the trust-first deterministic path on your repository:

```bash
riskmap analyze \
  --mode full \
  --analysis-engine deterministic \
  --no-llm \
  --output-dir ./.riskmap
```

Open the main report:

```bash
cat ./.riskmap/report.md
```

If you want to try the bundled sample first:

```bash
riskmap analyze --sample --no-llm --output-dir ./.riskmap
```

## Example Output

```md
# Risk Analysis Report

## Summary

| Severity | Count |
|---|---:|
| critical | 0 |
| high | 1 |
| medium | 1 |
| low | 0 |

## Top Actions for Next Sprint

- Add API/service tests for endpoint 'create_order', including success and error paths.
- Implement handler logic for transition 'pending -> cancelled' or remove stale declaration.
```

## What You Get

- `report.md`: human-readable summary and top actions
- `findings.json`: machine-readable findings
- `test_plan.json`: prioritized test recommendations

For all flags and modes:

```bash
riskmap analyze --help
```

## PR Workflow

Create a deterministic baseline on `main`:

```bash
riskmap analyze \
  --mode full \
  --analysis-engine deterministic \
  --no-llm \
  --output-dir ./.riskmap/baseline
```

Run PR-scoped analysis on your feature branch:

```bash
riskmap analyze \
  --mode pr \
  --base main \
  --baseline-graph ./.riskmap/baseline/graph.json \
  --only-new \
  --output-dir ./.riskmap
```

For PR delta to work, the baseline directory must contain both `graph.json` and `findings.json`.

## Works Best For

- backend teams doing pre-merge or pre-release reviews
- repositories with explicit HTTP/write flows and tests
- teams that want advisory signals before enabling CI gates

## Current Scope

- Stack plugins: `fastapi_pytest`, `django_drf`, `express_node`
- Ingress families: `http`, `webhook`, `job`, `cli_task`, `event_consumer`
- Issue types: missing tests on critical endpoints, missing transition handlers, dependency/version policy risks, contract mismatches, write/session integrity issues, and selected UI regressions

## Limits

- Not a business-logic verifier
- Not a generic multi-language SAST replacement
- Unknown stacks fall back to advisory mode and may produce partial results

## API

If you need a local API service:

```bash
pip install -e '.[api]'
riskmap-api
```

Optional hardening is available through environment variables such as `AIRISK_API_TOKEN`, `AIRISK_API_RATE_LIMIT_PER_MINUTE`, and `AIRISK_API_MAX_BODY_BYTES`.

## Development

```bash
make install
make test
```

## Docs

- `docs/ru.md`
- `docs/compatibility.md`
- `docs/deployment-hardening.md`
- `docs/plugin-contract.md`

## Open Source

- License: `LICENSE` (MIT)
- Contributing: `CONTRIBUTING.md`
- Security Policy: `SECURITY.md`
- Changelog: `CHANGELOG.md`
