# AI Risk Manager

AI Risk Manager is an OSS QA risk-mapping tool for Python backend services (FastAPI and Django/DRF).

It helps answer two questions before merge/release:

- Which backend flows are risky right now?
- Which tests should we add first?

## Start Here (5 Minutes)

1. Install:

```bash
pip install -e '.[dev]'
```

2. Run on bundled sample:

```bash
riskmap analyze --sample --no-llm --output-dir ./.riskmap
```

Optional sample override:

```bash
AIRISK_SAMPLE_REPO=/path/to/local/sample riskmap analyze --sample --no-llm
```

3. Open the main output:

```bash
cat ./.riskmap/report.md
```

If this looks useful, run it on your repo.

## Run On Your Repository

1. Create baseline from `main`:

```bash
riskmap analyze --no-llm --output-dir ./.riskmap/baseline
```

2. Run PR-scoped analysis on your branch:

```bash
riskmap analyze \
  --mode pr \
  --base main \
  --baseline-graph ./.riskmap/baseline/graph.json \
  --only-new \
  --output-dir ./.riskmap
```

3. Review:

- `./.riskmap/pr_summary.md`
- `./.riskmap/findings.json`

## What To Read First In Outputs

- `report.md`: human-readable summary and top actions.
- `pr_summary.md`: compact PR comment style view (PR mode).
- `findings.json`: machine-readable findings for automation.
- `test_plan.json`: prioritized recommended tests.

## Who This Is For Right Now

- FastAPI teams using pytest.
- Django/DRF teams.
- Teams that want release-risk visibility in PR/CI.
- Teams that need actionable test recommendations, not generic warnings.

## Current Scope (v0.1.x)

- Current stack plugins:
  - `fastapi_pytest` (mature path)
  - `django_drf` (verified path, default auto support level `l2` on clean preflight)
- Local/CI assistant for QA risk mapping.
- Not a generic multi-language SAST replacement.
- API adapter is local/internal oriented (no auth, no multi-tenant guarantees).
- Universal/mixed-stack strategy is roadmap direction, not current shipped behavior.

## What It Analyzes

Extractor focus:

- write endpoints (`POST|PUT|PATCH|DELETE`)
- endpoint-model links (Pydantic request/response models)
- declared vs handled state transitions
- pytest tests and test HTTP calls mapped to endpoints

Deterministic rules include:

- `critical_path_no_tests`
- `missing_transition_handler`
- `broken_invariant_on_transition`
- `dependency_risk_policy_violation`

Optional semantic AI stage can add extra grounded findings with evidence refs.

## CI Rollout (Safe By Default)

`ci_mode`:

- `advisory` (default): report only, never fail on new findings.
- `soft`: fail when new `high|critical` findings exist.
- `block-new-critical`: fail only for `new + critical + high confidence + verified evidence`.

`support_level`:

- `auto` (default): `unknown -> l0`, known plugin stacks -> `l2`.
- In `auto`, preflight warnings downgrade support level by one step (`l2 -> l1`, `l1 -> l0`).
- `l0`: block modes downgraded to advisory.
- `l1`: `block-new-critical` downgraded to `soft`.
- `l2`: full mode behavior.

## Most Useful CLI Flags

```bash
riskmap analyze [PATH]
riskmap analyze --sample
riskmap analyze --mode pr --base main --baseline-graph ./.riskmap/baseline/graph.json
riskmap analyze --only-new
riskmap analyze --ci-mode advisory|soft|block-new-critical
riskmap analyze --support-level auto|l0|l1|l2
riskmap analyze --risk-policy conservative|balanced|aggressive
riskmap analyze --analysis-engine deterministic|hybrid|ai-first
riskmap analyze --provider auto|api|cli
riskmap analyze --no-llm
riskmap analyze --fail-on-severity high
riskmap analyze --suppress-file .airiskignore
```

Dependency policy profiles:

- `conservative`: `direct_reference`, `wildcard_version`
- `balanced` (default): conservative + `range_not_pinned`
- `aggressive`: balanced + `unpinned_version`

Severity by dependency scope:

- `runtime`: direct/wildcard -> `high`, range/unpinned -> `medium`
- `development`: direct/wildcard -> `medium`, range/unpinned -> `low`

## API Quick Start (Sync)

Install API extras:

```bash
pip install -e '.[api]'
```

Start server:

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
| 2 | Unsupported repository for current extractor plugins |
| 3 | `--fail-on-severity` or `--ci-mode` threshold reached |

## Suppressions (`.airiskignore`)

```yaml
- key: "critical_path_no_tests:api:app:api.py:create_order"
- rule: "missing_transition_handler"
  file: "app/orders.py"
```

## Policy Overrides (`.airiskpolicy`)

Use `.airiskpolicy` (JSON) to tune per-rule behavior without code forks.

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

Rule fields:

- `enabled` (`true|false`): include or disable findings for this rule.
- `severity` (`critical|high|medium|low`): override severity in outputs and threshold checks.
- `gate`:
  - `default`: finding participates in `--fail-on-severity` and CI blocking modes.
  - `never_block`: finding is reported but ignored for exit-code blocking decisions.

## Trust-First Eval Artifacts

Weekly eval workflow publishes:

- `eval/results/trust_gate.json`
- `eval/results/trust_history.jsonl`
- `eval/results/trust_trend.json`
- `eval/results/trust_trend.md`

Thresholds are versioned in `eval/trust_thresholds.json`.

## Troubleshooting

- `exit 1`: choose another provider or run with `--no-llm`.
- `exit 2`: repository does not match supported plugin patterns in strict levels (`--support-level l1|l2`).
- Empty PR findings: check baseline graph and changed file detection.
- Unknown stack with default `--support-level auto`: run continues in L0 advisory mode.
- `--sample` cannot find bundled sample: set `AIRISK_SAMPLE_REPO`.

## Development Commands

```bash
make install
make install-api
make test
make analyze-demo
make serve-api
make eval
```

`make eval` enforces trust gates by default.
Use `AIRISK_EVAL_ENFORCE_THRESHOLDS=0 make eval` for non-blocking eval runs.

## Docs Map

- `docs/ru.md`: Russian quick guide
- `docs/compatibility.md`: CLI/API/JSON compatibility policy
- `ROADMAP.md`: MVP now / next
- `BACKLOG_TRUST_FIRST.md`: trust-first delivery backlog and KPI gates
- `SUPPORT.md`: support channels

## Open Source

- License: `LICENSE` (MIT)
- Contributing: `CONTRIBUTING.md`
- Code of Conduct: `CODE_OF_CONDUCT.md`
- Security Policy: `SECURITY.md`
- Changelog: `CHANGELOG.md`
