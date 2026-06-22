# Contributing

Thanks for contributing to AI Risk Manager.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

`.[dev]` already includes API dependencies (`fastapi`, `uvicorn`, `httpx`) for local API testing.

## Local checks

```bash
make test
make eval
make analyze-demo
```

You can also run quality gates directly:

```bash
ruff check src tests scripts
mypy src
pytest --cov=ai_risk_manager --cov-fail-under=80
```

## Pull request workflow

1. Create a focused branch.
2. Add tests for behavior changes.
3. Keep CLI and JSON contract backward compatible for patch/minor releases.
4. Open a PR with problem statement, changes, and test evidence.

## Release flow

1. Choose the next semantic version and update `pyproject.toml`, `CHANGELOG.md`, and release notes in one reviewed PR.
2. Ensure `main` passes quality, mutation, performance, artifact smoke, dependency audit, and eval workflows.
3. Create and push an annotated `vX.Y.Z` tag that exactly matches `project.version`.
4. Create a draft GitHub Release for that tag and review its notes and known limitations.
5. Publish the GitHub Release. The tag-bound release workflow rebuilds once, smoke-tests distributions, emits checksums and a reproducible SBOM, attests build provenance, and publishes to PyPI through OIDC in the `pypi` environment.
6. Verify the GitHub attestation, workflow artifacts, PyPI metadata, and clean installation before announcing the release.

Configure the `pypi` GitHub environment with required reviewers and register this repository/workflow as a PyPI trusted publisher before the first publication. No long-lived PyPI token is supported.

### Rollback

Published package files and tags are immutable release evidence; do not rewrite or silently replace them. For a release defect:

1. Yank the affected PyPI version with a reason and mark the GitHub Release as affected.
2. Revert or forward-fix on `main`, run the full release gates, and publish a new patch version.
3. Verify the replacement package from a clean environment and update the affected release notes with the successor version.

There are currently no database or data migrations. Runtime rollback is therefore consumer-controlled: pin the last known-good package version until the patch is verified.
