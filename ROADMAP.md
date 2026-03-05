# Roadmap

## MVP now (v0.1.x)

- Shared core pipeline (`run_pipeline`) with transport adapters:
  - CLI (`riskmap`)
  - HTTP API (`/v1/analyze`, sync)
- Static stack discovery + collector plugin dispatch
- Current extractor plugins:
  - `fastapi_pytest` (mature)
  - `django_drf` (verified)
- Deterministic rule engine + optional LLM enrichment
- PR mode with impacted scope and fallback strategy
- Suppressions via `.airiskignore`
- Stable JSON metadata (`schema_version`, `generated_at`, `tool_version`)
- CI rollout controls:
  - `ci_mode`: `advisory|soft|block-new-critical`
  - `support_level`: `auto|l0|l1|l2`
  - auto support-level downgrade on preflight warnings (`l2 -> l1`, `l1 -> l0`)
  - effective CI mode matrix with auditable summary output
- Trust-first quality controls:
  - eval trust gates with versioned thresholds
  - weekly trend tracking artifacts from eval runs
  - expansion readiness gate artifact (`eval/results/expansion_gate.json`)
- Explainability and risk precision improvements:
  - confidence/evidence-based ranking in reports
  - dependency policy profiles with scope-aware severity

## Next (Post Stage 10, Gate-Based)

- Universal core, contract-driven expansion, and service hardening are complete through Stage 10.
- Next delivery focus:
  - Stage 11: capability-depth expansion for existing stacks (`express_node` first) via shared signal model.
    - P0: data-integrity and boundary contracts (write binding, write scope, stale-write conflict guards, session lifecycle consistency).
    - P1: frontend security sinks (stored-XSS unsafe HTML rendering).
    - P2: optional low-impact ergonomics heuristics (UI/page-state quality) behind conservative policy defaults.
  - Stage 12: support-level promotion for new capability pack with parity eval and trust-gate stability checks.

## Delivery Model (Stage-Gate)

- Development progresses by completion gates, not fixed calendar dates.
- Transition to the next stage is allowed only when all gates pass:
  - implementation is complete for the current stage
  - `pytest` is green
  - trust/eval gates pass for touched behavior
  - docs/contracts are updated when interfaces or semantics change

## Execution Sequence (By Completion)

1. [x] Stage 1: pipeline contract stabilization and stage decomposition.
2. [x] Stage 2: coverage mapping quality improvements.
3. [x] Stage 3: policy engine externalization (`.airiskpolicy`).
4. [x] Stage 4: next stack expansion behind trust gates.
5. [x] Stage 5: universal plugin contract (v1) + conformance gates.
6. [x] Stage 6: universal risk capability pack (`side_effect_emit_contract`, `authorization_boundary_enforced`).
7. [x] Stage 7: contract-driven stack expansion (parity + trust gates).
8. [x] Stage 8: service-grade hardening for deployment scenarios.
9. [ ] Stage 11: capability-depth expansion for existing stacks.
10. [ ] Stage 12: capability-pack promotion and trust-gate stabilization.
