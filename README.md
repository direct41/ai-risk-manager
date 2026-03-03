# AI Risk Manager

AI Risk Manager is a QA risk-mapping tool for Python backends (FastAPI and Django/DRF).

It answers two practical questions before merge/release:
- Which backend flows are risky now?
- Which tests should we add first?

## Quick Start

Install:

```bash
pip install -e '.[dev]'
```

Run on bundled sample:

```bash
riskmap analyze --sample --no-llm --output-dir ./.riskmap
cat ./.riskmap/report.md
```

Optional sample override:

```bash
AIRISK_SAMPLE_REPO=/path/to/local/sample riskmap analyze --sample --no-llm
```

## PR Workflow (Recommended)

1. Build deterministic baseline on `main`:

```bash
riskmap analyze \
  --mode full \
  --no-llm \
  --analysis-engine deterministic \
  --output-dir ./.riskmap/baseline
```

2. Run PR-scoped analysis on feature branch:

```bash
riskmap analyze \
  --mode pr \
  --base main \
  --baseline-graph ./.riskmap/baseline/graph.json \
  --only-new \
  --output-dir ./.riskmap
```

Important for PR delta (`new/resolved/unchanged`):
- baseline folder must contain both `graph.json` and `findings.json`.

## Key Outputs

- `report.md`: human-readable summary and top actions.
- `pr_summary.md`: compact PR view (PR mode).
- `findings.json`: machine-readable findings.
- `test_plan.json`: prioritized test recommendations.
- `graph.json` and `graph.analysis.json`: analysis graph used for findings (may include semantic enrichment).
- `graph.deterministic.json`: deterministic graph before semantic enrichment.
- `run_metrics.json`: quality and run metrics.

## Current Scope (v0.1.x)

- Stack plugins:
  - `fastapi_pytest`
  - `django_drf`
- Local/CI assistant for risk mapping.
- Not a generic multi-language SAST replacement.
- API is local/internal oriented (no auth, no multi-tenant guarantees).

Deterministic rules:
- `critical_path_no_tests`
- `missing_transition_handler`
- `broken_invariant_on_transition`
- `dependency_risk_policy_violation`
- `missing_required_side_effect` (contract-level; plugin extraction in progress)
- `critical_write_missing_authz` (contract-level; plugin extraction in progress)

## CI Rollout Controls

`ci_mode`:
- `advisory` (default): never fails build.
- `soft`: fails on new `high|critical`.
- `block-new-critical`: fails only on `new + critical + high confidence + verified evidence`.

`support_level`:
- `auto` (default): `unknown -> l0`, known stacks -> `l2`.
- preflight warnings in `auto` downgrade one step (`l2 -> l1`, `l1 -> l0`).
- `l0`: blocking modes downgraded to advisory.
- `l1`: `block-new-critical` downgraded to `soft`.
- `l2`: full behavior.

## Useful CLI Flags

```bash
riskmap analyze [PATH]
riskmap analyze --sample
riskmap analyze --mode pr --base main --baseline-graph ./.riskmap/baseline/graph.json
riskmap analyze --analysis-engine deterministic|hybrid|ai-first
riskmap analyze --provider auto|api|cli
riskmap analyze --no-llm
riskmap analyze --only-new
riskmap analyze --min-confidence high|medium|low
riskmap analyze --ci-mode advisory|soft|block-new-critical
riskmap analyze --support-level auto|l0|l1|l2
riskmap analyze --risk-policy conservative|balanced|aggressive
riskmap analyze --fail-on-severity critical|high|medium|low
riskmap analyze --suppress-file .airiskignore
```

Dependency policy profiles:
- `conservative`: `direct_reference`, `wildcard_version`
- `balanced` (default): conservative + `range_not_pinned`
- `aggressive`: balanced + `unpinned_version`

## Suppressions and Policy

Suppressions (`.airiskignore`):

```yaml
- key: "critical_path_no_tests:api:app:api.py:create_order"
- rule: "missing_transition_handler"
  file: "app/orders.py"
```

Policy overrides (`.airiskpolicy`):

```json
{
  "version": 1,
  "rules": {
    "critical_path_no_tests": {
      "enabled": true,
      "severity": "medium",
      "gate": "never_block"
    }
  }
}
```

## API Quick Start

Install API extras:

```bash
pip install -e '.[api]'
```

Run server:

```bash
riskmap-api
```

Health:

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

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Explicit provider unavailable (`--provider api|cli`) |
| 2 | Unsupported repository for strict extractor modes |
| 3 | `--fail-on-severity` or `--ci-mode` threshold reached |

## Eval Artifacts

Weekly eval workflow publishes:
- `eval/results/trust_gate.json`
- `eval/results/trust_history.jsonl`
- `eval/results/trust_trend.json`
- `eval/results/trust_trend.md`
- `eval/results/expansion_gate.json`
- `eval/results/plugin_conformance.json`
- `eval/results/support_level_promotion.json`

Use `make eval` locally.
Use `AIRISK_EVAL_ENFORCE_THRESHOLDS=0 make eval` for non-blocking local runs.

## Troubleshooting

- `exit 1`: choose another provider or use `--no-llm`.
- `exit 2`: repository does not match supported plugin patterns in strict levels.
- Empty PR findings: verify baseline files and changed-files detection.
- Unknown stack with `--support-level auto`: run continues in L0 advisory mode.

## Development

```bash
make install
make install-api
make test
make analyze-demo
make serve-api
make eval
python scripts/init_stack_plugin.py --stack-id flask_pytest
```

## Docs Map

- `docs/ru.md`: Russian quick guide
- `docs/compatibility.md`: CLI/API/JSON compatibility policy
- `docs/capability-signals.md`: stack-agnostic signal model
- `docs/plugin-contract.md`: plugin contract v1 and conformance rules
- `docs/stack-expansion-candidates.md`: ranked shortlist for next stack expansion
- `ROADMAP.md`: product roadmap
- `BACKLOG_TRUST_FIRST.md`: trust-first backlog and KPI gates
- `SUPPORT.md`: support channels

## Open Source

- License: `LICENSE` (MIT)
- Contributing: `CONTRIBUTING.md`
- Code of Conduct: `CODE_OF_CONDUCT.md`
- Security Policy: `SECURITY.md`
- Changelog: `CHANGELOG.md`
