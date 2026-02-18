# AI Risk Manager

MVP CLI tool for deterministic + optional LLM-assisted QA risk analysis.

## Install

```bash
pip install -e .
```

Requirements:
- Python 3.11+

## Usage

```bash
riskmap analyze
riskmap analyze --mode pr --base main
riskmap analyze --mode pr --base main --baseline-graph ./.riskmap/baseline/graph.json
riskmap analyze --provider auto
riskmap analyze --provider api
riskmap analyze --provider cli
riskmap analyze --no-llm
riskmap analyze --output-dir ./.riskmap
```

## Provider selection

- `--provider auto` (default)
  - local: `cli -> api -> no-llm`
  - CI: `api -> no-llm`
- `--provider api` uses API credentials from environment variables.
- `--provider cli` uses installed AI CLI (for local use).
- `--no-llm` forces deterministic mode.

Supported API credentials:
- `OPENAI_API_KEY`
- `LITELLM_API_KEY`
- `ANTHROPIC_API_KEY` (with OpenAI-compatible endpoint config when needed)

## Output artifacts

Artifacts are written to `.riskmap/` by default:

- `report.md`
- `graph.json`
- `findings.raw.json`
- `findings.json`
- `test_plan.json`
- `pr_summary.md` (PR mode only)

Notes:
- In PR mode, `graph.json` contains the graph for the current analysis scope (`impacted` or `full_fallback`), not always the full repository graph.
- For local PR simulation you can override changed files with `AIRISK_CHANGED_FILES`, e.g.:

```bash
AIRISK_CHANGED_FILES=app/api.py riskmap analyze --mode pr --base main --baseline-graph ./.riskmap/baseline/graph.json
```

## Exit Codes

- `0`: success
- `1`: explicit provider unavailable (`--provider api|cli` misconfigured)
- `2`: pre-flight unsupported repository for MVP

## Evaluation Suite

Run the eval suite locally:

```bash
python scripts/run_eval_suite.py
```

Results are written to `eval/results/summary.md` and `eval/results/summary.json`.

## CI Workflows

- `.github/workflows/risk-analysis.yml`: baseline on `main` + PR analysis with sticky PR comment.
- `.github/workflows/eval-suite.yml`: scheduled/manual quality checks over eval repositories.
