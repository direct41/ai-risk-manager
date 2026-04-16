# Workspace and Monorepo Usage

AI Risk Manager currently analyzes one project root at a time.

For workspaces and monorepos, use the package or service directory that owns the changed code, not the outer workspace directory.

## Why

PR relevance depends on two paths matching:

- changed files from git
- source files discovered by the selected risk profiles

If the outer directory is only a workspace container, it may not be a git repository or may not represent one deployable app. In that case the PR summary can become noisy because changed files and project structure are not aligned.

## Recommended Invocation

Use the app package root:

```bash
cd shop-frontend
riskmap analyze \
  --mode pr \
  --base main \
  --analysis-engine deterministic \
  --no-llm \
  --output-dir ./.riskmap
```

For another package, run the same command from that package:

```bash
cd shop-landing
riskmap analyze \
  --mode pr \
  --base main \
  --analysis-engine deterministic \
  --no-llm \
  --output-dir ./.riskmap
```

## CI Pattern

Run one job per changed package when the repository has multiple independently deployable apps.

Example:

```bash
riskmap analyze packages/web --mode pr --base main --output-dir packages/web/.riskmap
riskmap analyze packages/api --mode pr --base main --output-dir packages/api/.riskmap
```

Keep `AIRISK_CHANGED_FILES` package-relative if you pass it manually:

```bash
AIRISK_CHANGED_FILES=app/pages/checkout/index.vue,app/components/cart/CartModal.vue \
  riskmap analyze shop-frontend --mode pr --base main --output-dir shop-frontend/.riskmap
```

## Current Limit

Automatic workspace discovery is intentionally not shipped yet.

The current rule is simple:

- if each package has its own `.git`, run inside that package
- if the monorepo has one shared `.git`, run against the package root and pass package-relative changed files when needed
- keep declared UI smoke config (`.riskmap-ui.toml`) in the same package root as the app

This keeps `ui_flow_risk` focused on the app that changed and avoids treating the whole workspace as one large UI surface.
