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

## Next (Post Stage 12, Architecture Reset)

- Universal core, contract-driven expansion, service hardening, capability-depth expansion, and pack-level promotion gates are complete through Stage 12.
- The next roadmap is now organized around architectural scaling constraints, not around isolated feature batches.
- Architecture decision record: [docs/architecture-next.md](docs/architecture-next.md)
- Next delivery focus:
  - Stage 13: generalize the analyzer around ingress-family contracts, not only HTTP write paths.
  - Stage 14: bring Stage 11 capability packs to parity across existing supported stacks.
  - Stage 15: add advisory-only AI extraction for partially supported repositories behind evidence and trust gates.
  - Stage 16: package an external plugin distribution model only after contracts and promotion logic are stable.

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
9. [x] Stage 11: capability-depth expansion for existing stacks.
10. [x] Stage 12: capability-pack promotion and trust-gate stabilization.
11. [x] Stage 13: ingress contract generalization beyond HTTP.
12. [ ] Stage 14: capability-pack parity across supported stacks.
13. [ ] Stage 15: advisory AI extraction for partially supported repositories.
14. [ ] Stage 16: external plugin distribution model.
