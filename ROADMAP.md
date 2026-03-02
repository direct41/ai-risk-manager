# Roadmap

## MVP now (v0.1.x)

- Shared core pipeline (`run_pipeline`) with transport adapters:
  - CLI (`riskmap`)
  - HTTP API (`/v1/analyze`, sync)
- Static stack discovery + collector plugin dispatch
- First extractor plugin: `fastapi_pytest`
- Deterministic rule engine + optional LLM enrichment
- PR mode with impacted scope and fallback strategy
- Suppressions via `.airiskignore`
- Stable JSON metadata (`schema_version`, `generated_at`, `tool_version`)
- CI rollout controls:
  - `ci_mode`: `advisory|soft|block-new-critical`
  - `support_level`: `auto|l0|l1|l2`
  - effective CI mode matrix with auditable summary output
- Trust-first quality controls:
  - eval trust gates with versioned thresholds
  - weekly trend tracking artifacts from eval runs
- Explainability and risk precision improvements:
  - confidence/evidence-based ranking in reports
  - dependency policy profiles with scope-aware severity

## Next

- Additional collector plugins beyond FastAPI
- Better test-to-endpoint mapping precision (path params, aliases, fixture-aware heuristics)
- Policy externalization (`.airiskpolicy`) for per-rule severity/gating tuning
- Additional rules for authorization and critical-path behavior patterns
- Hardening for service deployment scenarios (auth, rate limits) after local/internal maturity

## Delivery Model (Stage-Gate)

- Development progresses by completion gates, not fixed calendar dates.
- Transition to the next stage is allowed only when all gates pass:
  - implementation is complete for the current stage
  - `pytest` is green
  - trust/eval gates pass for touched behavior
  - docs/contracts are updated when interfaces or semantics change

## Execution Sequence (By Completion)

1. Stage 1: pipeline contract stabilization and stage decomposition.
2. Stage 2: coverage mapping quality improvements.
3. Stage 3: policy engine externalization (`.airiskpolicy`).
4. Stage 4: next stack expansion behind trust gates.
