# AI Risk Manager

AI Risk Manager is an OSS risk-mapping tool with one shared analysis core and two adapters:

- `CLI` (`riskmap analyze ...`)
- `HTTP API` (`/v1/analyze`)

The analysis core is deterministic-first (`collector -> graph -> rules`) with optional LLM enrichment (`risk agent`, `qa strategy agent`).

## Scope (v0.1.x)

Current extractor support:

- `fastapi_pytest` stack plugin (FastAPI + pytest patterns)

This project is still intentionally narrow in extraction scope, but architecture is adapter/plugin based:

- one core pipeline (`run_pipeline`)
- stack detection + collector plugin dispatch
- transport adapters (CLI/API)

## Quickstart

```bash
pip install -e '.[dev]'
riskmap analyze --sample --output-dir ./.riskmap
cat ./.riskmap/report.md
```

Expected artifacts (`--format both`, default):

- `.riskmap/report.md`
- `.riskmap/graph.json`
- `.riskmap/findings.raw.json`
- `.riskmap/findings.json`
- `.riskmap/test_plan.json`
- `.riskmap/pr_summary.md` (PR mode only)

## CLI Usage

```bash
riskmap analyze [PATH]
riskmap analyze --sample
riskmap analyze --mode pr --base main --baseline-graph ./.riskmap/baseline/graph.json
riskmap analyze --provider auto|api|cli
riskmap analyze --no-llm
riskmap analyze --format md|json|both
riskmap analyze --fail-on-severity high
riskmap analyze --suppress-file .airiskignore
```

## API Usage (sync)

Install API dependencies first:

```bash
pip install -e '.[api]'
```

Start server:

```bash
riskmap-api
```

Healthcheck:

```bash
curl -s http://127.0.0.1:8000/healthz
```

Analyze:

```bash
curl -s -X POST http://127.0.0.1:8000/v1/analyze \
  -H 'Content-Type: application/json' \
  -d '{
    "path": ".",
    "mode": "full",
    "provider": "auto",
    "no_llm": true,
    "output_dir": ".riskmap",
    "format": "both"
  }'
```

`POST /v1/analyze` request fields are compatible with `RunContext`:

- `path`, `mode`, `base`, `no_llm`, `provider`, `baseline_graph`, `output_dir`, `format`, `fail_on_severity`, `suppress_file`, `sample`

Response always includes:

- `exit_code`
- `notes`
- `output_dir`
- `artifacts`
- `result` (`null` for `exit_code` 1/2)

## Provider Selection

- `--provider auto` (default)
  - local: `cli -> api -> no-llm`
  - CI: `api -> no-llm`
- `--provider api`: uses API credentials from env vars.
- `--provider cli`: uses installed AI CLI.
- `--no-llm`: deterministic-only mode.

Supported credentials:

- `OPENAI_API_KEY`
- `LITELLM_API_KEY`
- `ANTHROPIC_API_KEY`

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Explicit provider unavailable (`--provider api|cli`) |
| 2 | Unsupported repository for current extractor plugins |
| 3 | `--fail-on-severity` threshold reached |

## Suppressions (`.airiskignore`)

Use suppressions to hide known noise:

```yaml
- key: "critical_path_no_tests:api:app:api.py:create_order"
- rule: "missing_transition_handler"
  file: "app/orders.py"
```

## What Good Output Looks Like

Example `report.md` excerpt:

```md
## Summary
| Severity | Count |
|---|---:|
| critical | 0 |
| high | 1 |

## Top Actions for Next Sprint
- Action: Add API/service tests for endpoint 'create_order'.
  Expected impact: reduce `critical_path_no_tests` risk around `app/api.py`.
```

## Glossary

- `Graph`: extracted nodes and edges from code/test structure.
- `Finding`: normalized risk record with severity, evidence, and action.
- `TestPlan`: prioritized test recommendations derived from findings.
- `analysis_scope`: `full`, `impacted`, or `full_fallback` for PR analysis.

## GitHub Actions Integration

Minimal job (fork-safe, no secrets):

```yaml
- run: pip install -e '.[dev]'
- run: riskmap analyze --no-llm --output-dir ./.riskmap
```

Recommended PR mode job:

```yaml
- run: |
    riskmap analyze \
      --mode pr \
      --base "${{ github.base_ref }}" \
      --provider auto \
      --baseline-graph ./.riskmap/baseline/graph.json \
      --output-dir ./.riskmap
```

## Troubleshooting

- `exit 1`: select another provider or run with `--no-llm`.
- `exit 2`: repo does not match supported stack plugins.
- Empty PR findings: ensure baseline graph exists and changed files are detected.

## Development Commands

```bash
make install
make test
make analyze-demo
make eval
```

## Docs

- `docs/ru.md`: short Russian guide
- `docs/compatibility.md`: CLI/API/JSON compatibility policy
- `ROADMAP.md`: MVP now / next
- `SUPPORT.md`: support channels
