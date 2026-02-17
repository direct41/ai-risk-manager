# AI Risk Manager

MVP CLI tool for deterministic + optional LLM-assisted QA risk analysis.

## Install

```bash
pip install -e .
```

## Usage

```bash
riskmap analyze
riskmap analyze --mode pr --base main
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

## Output artifacts

Artifacts are written to `.riskmap/` by default:

- `report.md`
- `graph.json`
- `findings.raw.json`
- `findings.json`
- `test_plan.json`
