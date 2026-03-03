# Deployment Hardening (API)

This checklist defines the minimum secure baseline for running `riskmap-api` outside a local-only setup.

## Threat Model (Concise)

- External caller can send untrusted JSON to `POST /v1/analyze`.
- Primary risks:
  - unauthorized analysis runs;
  - request flooding / oversized payload abuse;
  - weak incident forensics when failures happen.
- Baseline controls already implemented:
  - optional token auth (`AIRISK_API_TOKEN`);
  - rate and payload guardrails (`AIRISK_API_RATE_LIMIT_PER_MINUTE`, `AIRISK_API_MAX_BODY_BYTES`);
  - correlation/audit controls (`X-Correlation-ID`, `AIRISK_API_AUDIT_LOG`, `api_audit.json`).

## Minimum Production Configuration

Set these variables in deployment:

```bash
AIRISK_API_HOST=0.0.0.0
AIRISK_API_PORT=8000
AIRISK_API_TOKEN=<strong-random-token>
AIRISK_API_RATE_LIMIT_PER_MINUTE=60
AIRISK_API_MAX_BODY_BYTES=262144
AIRISK_API_AUDIT_LOG=/var/log/ai-risk-manager/api-audit.jsonl
```

Security notes:
- Keep `AIRISK_API_TOKEN` in a secret manager, never in Git.
- Place API behind a reverse proxy (TLS termination + ingress ACL).
- Restrict access to trusted networks and CI runners only.
- Mount audit log path to persistent storage with rotation policy.

## Minimal Security Checklist

- [ ] API is reachable only through trusted ingress (VPN/private network/WAF).
- [ ] `AIRISK_API_TOKEN` is set and rotated on schedule.
- [ ] Rate limit and payload limit are enabled (non-zero).
- [ ] Audit trail is persisted (`AIRISK_API_AUDIT_LOG`) and retained.
- [ ] Correlation IDs are propagated from caller (`X-Correlation-ID`) in CI integrations.
- [ ] API process runs as a non-root user.
- [ ] Container/host filesystem is read-only except configured output and log paths.
- [ ] Dependency updates and quality gates (`ruff`, `mypy`, `pytest`) are green before deploy.

## Failure Diagnostics Playbook

For `500` responses:
1. Capture `correlation_id` and `diagnostic_id` from response payload.
2. Find matching event in `AIRISK_API_AUDIT_LOG` (or `api_audit.json` in run output dir).
3. Inspect `error_type` and `error_detail` in audit event.
4. Re-run locally with same input and correlation ID for deterministic triage.

## Known Limits

- In-memory rate limiter is per-process; use external gateway limits for multi-instance deployments.
- Token auth is single shared secret (not per-tenant IAM).
- Audit events are best-effort writes; failures to write logs do not block analysis execution.
