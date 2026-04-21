# UI Flow Risk Pilots

This log records real-repository checks used to tune `ui_flow_risk`.

The goal is not to prove broad frontend coverage.
The goal is to catch whether the PR summary becomes useful or noisy before adding heavier browser features.

## Pilot 1: `projects/notes-buggy-pet`

Repository shape:

- Express app with vanilla `public/` UI
- files: `public/index.html`, `public/app.js`, `public/styles.css`

Synthetic changed files:

```bash
AIRISK_CHANGED_FILES=public/app.js,public/index.html,public/styles.css \
  riskmap analyze /Users/andry/projects/notes-buggy-pet \
  --mode pr --base main --analysis-engine deterministic --no-llm
```

Observed:

- initial `ui_flow_risk` missed the UI because it expected routed frontend structure
- after tuning, vanilla `public/` app shells map to `app_shell`
- PR summary now prioritizes changed-scope risk before repo-wide findings

Decision:

- keep vanilla public/static shell detection
- require `index.html` plus a shell asset to avoid treating lone static assets as UI apps

## Pilot 2: `work/rnd-autotests/1win-shop/shop-frontend`

Repository shape:

- Nuxt/Vue frontend package
- app-dir layout under `app/`
- workspace outer directory is not a single git repo

Synthetic changed files:

```bash
AIRISK_CHANGED_FILES=app/pages/checkout/index.vue,app/components/product/ProductGallery.vue,app/composables/checkout/useCheckoutState.ts \
  riskmap analyze /Users/andry/work/rnd-autotests/1win-shop/shop-frontend \
  --mode pr --base main --analysis-engine deterministic --no-llm
```

Observed:

- `ui_flow_risk` detected Vue/Nuxt UI surface
- route labels initially included suffix noise such as `checkout/vue`
- `app/components/...` was initially treated as a route because `app/` was too broad
- repo-wide dependency and generated-test findings could dominate the PR summary

Decision:

- strip UI file extensions from journey labels
- treat `app/**/page.*` style files as app-dir routes, but not all `app/` files
- cap repeated repo-wide rule findings in PR summary when changed scope is known
- keep full findings available in `findings.json` and `report.md`

## Pilot 3: `work/rnd-autotests/1win-shop/shop-landing`

Repository shape:

- Nuxt/Vue frontend package
- classic `pages/`, `components/`, `composables/` layout

Synthetic changed files:

```bash
AIRISK_CHANGED_FILES=pages/product/[slug].vue,components/CartModal.vue,composables/useCart.ts \
  riskmap analyze /Users/andry/work/rnd-autotests/1win-shop/shop-landing \
  --mode pr --base main --analysis-engine deterministic --no-llm
```

Observed:

- `pages/product/[slug].vue` maps to `product/[slug]`
- `components/CartModal.vue` maps to shared component target `cartmodal`
- PR summary stays short after repeated repo-wide finding cap

Decision:

- current Nuxt/Vue lexical mapping is good enough for declared-smoke MVP
- do not add screenshot diffing or browser matrix until declared smoke usage is validated

## Product Lessons

- Package root selection matters more than automatic workspace traversal right now.
- Clean labels are part of signal quality. A correct risk with a noisy label feels untrustworthy.
- PR comments should prioritize changed-scope findings and keep repo-wide scans in detailed artifacts.
- `ui_flow_risk` should stay opt-in for browser execution through `.riskmap-ui.toml`.
- Declared smoke commands are disabled by default; set `AIRISK_UI_SMOKE_ENABLE_COMMANDS=1` only for trusted repositories.

## Next Validation

Before screenshot or cross-browser work:

- run at least one declared smoke command in a trusted real frontend package with `AIRISK_UI_SMOKE_ENABLE_COMMANDS=1`
- confirm failed smoke appears as `ui_journey_smoke_failed`
- confirm successful smoke adds notes without findings
- collect whether QA users prefer journey IDs such as `checkout` or test-suite tags such as `@checkout`
