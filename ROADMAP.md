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

## Next

- Additional collector plugins beyond FastAPI
- Additional rules for dependency and authorization risk patterns
- Better test-to-endpoint mapping precision
- Optional blocking mode rollout by severity threshold
- Hardening for service deployment scenarios (auth, rate limits) after local/internal maturity
