# Performance SLOs

## Scope and success criteria

The guarded path is a cold Python process running a deterministic full-repository analysis and writing all JSON and Markdown artifacts. It excludes optional LLM calls, GitHub network latency, and benchmark checkout time because those are external integration paths with separate timeout controls.

| Workload | Repository files | p95 latency SLO | Peak RSS SLO | Owner |
| --- | ---: | ---: | ---: | --- |
| small | 50 | 750 ms | 192 MB | analyzer pipeline |
| medium | 250 | 1,500 ms | 256 MB | analyzer pipeline |
| large | 1,000 | 5,000 ms | 384 MB | analyzer pipeline |

The machine-readable contract is [`performance/slo.json`](../performance/slo.json). Any latency or memory breach fails CI. Budgets intentionally include headroom for shared runners; they are regression limits, not marketing claims about all repositories.

## Baseline and measurement method

On 2026-06-22, Python 3.13.2 on an arm64 development host produced this three-run baseline:

| Workload | p50 / p95 wall | p50 / p95 CPU | Peak RSS | Artifact output |
| --- | ---: | ---: | ---: | ---: |
| small | 143 / 168 ms | 99 / 102 ms | 30.23 MB | 57,699 bytes |
| medium | 225 / 226 ms | 182 / 182 ms | 31.67 MB | 252,269 bytes |
| large | 631 / 631 ms | 583 / 584 ms | 38.25 MB | 984,850 bytes |

Each repetition uses a new Python process and output directory. The workload generator creates FastAPI route modules and test files deterministically. Wall time includes imports, collection, graph/rule/trust/triage processing, report rendering, and artifact writes. CPU and peak RSS come from process resource usage; artifact bytes provide a stable I/O-volume measure.

Run locally:

```bash
make performance
```

## Bottleneck analysis

No release-blocking hotspot is present at the current scale. Increasing the workload from 50 to 1,000 files (20x) increases p50 wall time by about 5.8x and peak RSS by about 1.3x. CPU time remains close to wall time, so the synthetic path is primarily single-process compute rather than blocked external I/O. Artifact volume reaches about 0.98 MB at 1,000 files and remains proportionate to graph and finding counts.

The synthetic workload is deliberately controlled. It does not prove performance for very large source files, monorepos, network filesystems, LLM providers, GitHub rate limits, browser smoke commands, or adversarial regex/AST inputs.

## Regression controls and next actions

GitHub Actions runs three cold repetitions for each workload, enforces the versioned SLOs, and uploads `performance-results.json`. A breach requires profiling the affected collector or pipeline stage before changing a budget. Budget increases require documented workload or runner evidence.

Performance readiness decision: **GO** for the deterministic analyzer up to the guarded 1,000-file workload.

Top optimization actions if evidence justifies them:

1. Add per-stage timing before optimizing a breached collector or report path.
2. Add a real-repository workload distribution after open-alpha telemetry is available.
3. Add separate GitHub/LLM/browser integration SLOs only where the project controls retries, timeouts, and failure budgets.
