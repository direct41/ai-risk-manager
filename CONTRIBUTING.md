# Contributing

Thanks for contributing to AI Risk Manager.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## Local checks

```bash
make test
make eval
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

## Release flow (MVP)

1. Update changelog/release notes.
2. Ensure `main` passes quality + eval workflows.
3. Tag release (`vX.Y.Z`).
4. Publish GitHub Release; optional PyPI publish for discoverability.
