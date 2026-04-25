## Summary

## Why this change

## What changed

## Testing

- [ ] `pytest --cov=ai_risk_manager --cov-fail-under=80`
- [ ] `python scripts/run_eval_suite.py`
- [ ] Updated docs/contracts if needed

## Release Manager / Public Artifact Review

- [ ] I reviewed every new or changed tracked file as public repository content.
- [ ] No local maintainer notes, `.riskmap` outputs, eval results, build artifacts, secrets, private URLs, or unnecessary identity metadata are included.
- [ ] Any new `docs/*.md` file is intentionally public and added to `.github/public-artifacts-allowlist.txt`.
- [ ] Package artifacts remain intentionally scoped by `MANIFEST.in`.
