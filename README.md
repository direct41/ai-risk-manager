# AI Risk Manager

AI Risk Manager is an OSS QA risk-mapping tool for FastAPI services.

It is built to answer one practical question before merge/release:

- Which backend flows are risky right now?
- What tests should we add first?

Under the hood, it runs one shared analysis core (`collector -> graph -> rules -> optional AI enrichment`) and exposes two adapters:

- `CLI` (`riskmap analyze ...`)
- `HTTP API` (`POST /v1/analyze`)

## What It Actually Analyzes (FastAPI)

Current stack plugin: `fastapi_pytest`.

The extractor focuses on:

- write endpoints (`POST|PUT|PATCH|DELETE`)
- endpoint-model links (Pydantic request/response models)
- declared vs handled state transitions
- pytest tests and test HTTP calls mapped to endpoints

Deterministic rules currently include:

- `critical_path_no_tests`
- `missing_transition_handler`
- `broken_invariant_on_transition`
- `dependency_risk_policy_violation`

Optional semantic AI stage can add extra grounded findings with evidence refs.

## Scope and Status (v0.1.x)

- Current maturity: MVP (`0.1.x`), focused on `fastapi_pytest` repositories.
- Intended usage: local/CI assistant for QA-risk mapping.
- Not a generic SAST replacement.
- API adapter is local/internal oriented (no auth, no multi-tenant guarantees).

## 2-Minute Demo

```bash
pip install -e '.[dev]'
riskmap analyze --sample --no-llm --output-dir ./.riskmap
cat ./.riskmap/report.md
```

Bundled sample output includes findings similar to:

- high: write endpoint `create_order` has no matching tests
- medium: declared transition `pending -> cancelled` has no handler

## What You Get After a Run

Default output (`--format both`):

- `.riskmap/report.md` - human-readable summary and top actions
- `.riskmap/findings.json` - normalized findings for automation
- `.riskmap/test_plan.json` - prioritized test recommendations
- `.riskmap/graph.json` - extracted graph
- `.riskmap/findings.raw.json` - deterministic findings before merge
- `.riskmap/run_metrics.json` - run quality/coverage proxies
- `.riskmap/pr_summary.md` - PR mode only (ranked by severity, confidence, evidence refs)

## Typical Workflow For a Real Repo

1. Create a baseline from `main`:

```bash
riskmap analyze --no-llm --output-dir ./.riskmap/baseline
```

2. On a feature branch, run PR-scoped analysis:

```bash
riskmap analyze \
  --mode pr \
  --base main \
  --baseline-graph ./.riskmap/baseline/graph.json \
  --only-new \
  --output-dir ./.riskmap
```

3. Inspect `./.riskmap/pr_summary.md` and `./.riskmap/findings.json`.

## CLI Usage

Core command:

```bash
riskmap analyze [PATH]
```

Useful variants:

```bash
riskmap analyze --sample
riskmap analyze --mode pr --base main --baseline-graph ./.riskmap/baseline/graph.json
riskmap analyze --provider auto|api|cli
riskmap analyze --no-llm
riskmap analyze --analysis-engine deterministic|hybrid|ai-first
riskmap analyze --only-new
riskmap analyze --min-confidence high|medium|low
riskmap analyze --ci-mode advisory|soft|block-new-critical
riskmap analyze --support-level auto|l0|l1|l2
riskmap analyze --risk-policy conservative|balanced|aggressive
riskmap analyze --format md|json|both
riskmap analyze --fail-on-severity high
riskmap analyze --suppress-file .airiskignore
```

Dependency policy profile behavior:

- `conservative`: reports only `direct_reference` and `wildcard_version`.
- `balanced` (default): `conservative` + `range_not_pinned`.
- `aggressive`: `balanced` + `unpinned_version`.
- Severity is context-aware by dependency scope:
- `runtime`: `direct_reference|wildcard_version -> high`, `range|unpinned -> medium`.
- `development`: `direct_reference|wildcard_version -> medium`, `range|unpinned -> low`.

## API Usage (sync)

Install API dependencies:

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

`POST /v1/analyze` fields are aligned with `RunContext`:

- `path`, `mode`, `base`, `no_llm`, `provider`, `baseline_graph`, `output_dir`, `format`, `fail_on_severity`, `suppress_file`, `sample`
- `analysis_engine`, `only_new`, `min_confidence`, `ci_mode`, `support_level`, `risk_policy`

Response always includes:

- `exit_code`
- `notes`
- `output_dir`
- `artifacts`
- `result` (`null` for `exit_code` 1/2)
- `summary` (`new_count`, `resolved_count`, `unchanged_count`, `fallback_reason`, `support_level_applied`, `verification_pass_rate`, `evidence_completeness`, `competitive_mode`)

## Provider Selection

- `--provider auto` (default)
  - local: `cli -> api -> no-llm`
  - CI: `api -> no-llm`
- `--provider api`: API credentials from env vars.
- `--provider cli`: installed AI CLI.
- `--no-llm`: deterministic-only mode.
- `--analysis-engine ai-first` (default): deterministic + semantic AI merged by fingerprint.
- `--analysis-engine deterministic`: semantic AI stage disabled.
- `--analysis-engine hybrid`: deterministic + semantic AI stage.

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
| 3 | `--fail-on-severity` or `--ci-mode` threshold reached |

## CI Modes

- `advisory` (default): never fail only because of new findings.
- `soft`: fail when any new `high|critical` finding exists.
- `block-new-critical`: fail only when a new `critical` finding is verified by evidence refs.

## Support Levels

- `auto` (default): chooses level by detected stack (`unknown -> l0`, known plugins -> `l2`).
- `l0`: generic/advisory mode, CI block modes are downgraded to advisory.
- `l1`: verified/adoption mode, `block-new-critical` is downgraded to `soft`.
- `l2`: strict mode, full CI policy behavior.

Effective CI mode matrix:

| support_level_applied | requested `ci_mode` | effective `ci_mode` |
|---|---|---|
| `l0` | `advisory` | `advisory` |
| `l0` | `soft` | `advisory` |
| `l0` | `block-new-critical` | `advisory` |
| `l1` | `advisory` | `advisory` |
| `l1` | `soft` | `soft` |
| `l1` | `block-new-critical` | `soft` |
| `l2` | `advisory` | `advisory` |
| `l2` | `soft` | `soft` |
| `l2` | `block-new-critical` | `block-new-critical` |

## Suppressions (`.airiskignore`)

Use suppressions for known noise:

```yaml
- key: "critical_path_no_tests:api:app:api.py:create_order"
- rule: "missing_transition_handler"
  file: "app/orders.py"
```

## When This Tool Is Useful

- You ship FastAPI endpoints and want a fast, repeatable risk scan before release.
- You need PR-level visibility on only new high-signal risks.
- You want to convert findings into concrete test actions, not just static warnings.

## When This Tool Is Not The Best Fit (yet)

- You need broad polyglot SAST across many languages/frameworks.
- You need hosted multi-tenant API with auth, quotas, and RBAC.
- Your stack does not resemble FastAPI + pytest patterns.

## GitHub Actions Integration

Minimal fork-safe job:

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

- `exit 1`: select another provider or use `--no-llm`.
- `exit 2`: repo does not match supported stack plugins in strict support levels (`--support-level l1|l2`).
- Empty PR findings: ensure baseline graph exists and changed files are detected.
- Unknown stack with default `--support-level auto`: run continues in L0 advisory mode.

## Development Commands

```bash
make install
make install-api
make test
make analyze-demo
make serve-api
make eval
```

`make eval` runs trust gates using thresholds from `eval/trust_thresholds.json`.
Set `AIRISK_EVAL_ENFORCE_THRESHOLDS=0` to run eval in non-blocking mode.

## Docs

- `docs/ru.md`: short Russian guide
- `docs/compatibility.md`: CLI/API/JSON compatibility policy
- `ROADMAP.md`: MVP now / next
- `BACKLOG_TRUST_FIRST.md`: Trust-first delivery backlog and KPI gates
- `SUPPORT.md`: support channels

## Open Source

- License: `LICENSE` (MIT)
- Contributing guide: `CONTRIBUTING.md`
- Code of conduct: `CODE_OF_CONDUCT.md`
- Security policy: `SECURITY.md`
- Changelog: `CHANGELOG.md`
