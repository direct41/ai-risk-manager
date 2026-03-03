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

## Next (Global, Gate-Based)

- Stage 6: Universal risk capability pack
  - Add stack-agnostic risk signals and deterministic rules for:
    - `side_effect_emit_contract`
    - `authorization_boundary_enforced`
  - Keep rule logic in shared core, with plugins only mapping framework syntax to common signals.
- Stage 7: Contract-driven stack expansion
  - Expand beyond FastAPI/Django only through the common signal contract.
  - Require parity eval cases and trust-gate pass for each added stack before support-level promotion.
- Stage 8: Service-grade hardening
  - Harden API/runtime for broader deployment scenarios:
    - authn/authz
    - rate limiting
    - operational controls (auditability, reliability guardrails)

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
6. [ ] Stage 6: universal risk capability pack (`side_effect_emit_contract`, `authorization_boundary_enforced`).
7. [ ] Stage 7: contract-driven stack expansion (parity + trust gates).
8. [ ] Stage 8: service-grade hardening for deployment scenarios.
