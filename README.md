# AI Risk Manager

AI Risk Manager is an OSS MVP CLI for QA risk mapping in FastAPI repositories.
It is not a generic SAST scanner. It focuses on two reliable risk classes in MVP:

- `critical_path_no_tests`
- `missing_transition_handler`

## Who Is This For?

- Backend team leads: quick release-risk visibility for PRs and CI.
- Solo developers: fast local QA risk feedback before merge.
- QA engineers and startup CTOs: test-priority signals and coverage blind spots.

## MVP Scope and Limits

Supported stack for MVP:

- Python 3.11+
- FastAPI code patterns
- pytest test patterns

Out of scope for MVP:

- Multi-language repositories
- Non-Python service stacks
- Full semantic/runtime analysis

## Quickstart in 3 Commands

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
| 2 | Unsupported repository for MVP preflight |
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
- `exit 2`: repo does not match FastAPI/pytest assumptions.
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
- `docs/compatibility.md`: CLI/JSON compatibility policy
- `ROADMAP.md`: MVP now / next
- `SUPPORT.md`: support channels
