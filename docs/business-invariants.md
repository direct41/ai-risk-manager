# Business Invariant Risk

`business_invariant_risk` is intentionally explicit.

The tool does not guess business rules from code.
The profile becomes applicable only when the repository owns an invariant spec.

## Current State

Implemented now:

- profile registration
- `.riskmap.yml` / `.riskmap.yaml` detection
- profile applicability in summaries:
  - `not_applicable` when no invariant spec exists
  - `partial` when an explicit invariant spec exists
- PR-scoped critical-flow rule:
  - emits `business_critical_flow_changed_without_check_delta`
  - only when changed non-check files match a declared critical flow
  - only when no changed test/smoke/e2e file matches the declared check tokens

Not implemented yet:

- full YAML schema validation
- state/auth/payment/admin invariant enforcement
- business-flow runtime validation
- AI interpretation of business rules

## Spec Location

Put the spec in the project root being analyzed:

```text
.riskmap.yml
```

For workspaces, this means the package or service root, not the outer workspace directory.

## Supported Shape

The current parser intentionally supports a narrow YAML-like shape under `critical_flows`.
It reads only `id`, optional `match`, and optional `checks`.
Other sections are allowed as documentation for future rule packs, but they are not enforced yet.

```yaml
critical_flows:
  - id: checkout
    description: User can complete checkout with a payable cart.
    match: [checkout, cart, billing]
    checks: [checkout]

state_invariants:
  - id: paid_orders_are_immutable
    description: Paid orders cannot be changed without an explicit refund or exchange flow.

auth_invariants:
  - id: account_pages_require_session
    description: Account pages must require an authenticated session.

payment_invariants:
  - id: payment_retry_is_idempotent
    description: Payment retry must not create duplicate charges.

admin_invariants:
  - id: admin_actions_are_role_gated
    description: Admin-only actions must require role checks.

negative_paths:
  - id: checkout_rejects_empty_cart
    description: Checkout must reject empty carts.
```

Semantics:

- `id`: stable critical-flow name shown in findings.
- `match`: lexical tokens or path fragments used to match changed non-check files. If omitted, the `id` is used.
- `checks`: lexical tokens or path fragments used to match changed test/smoke/e2e files. If omitted, `match` tokens are used.

The first rule is PR-only:

```text
changed critical-flow file + no changed matching check file
=> business_critical_flow_changed_without_check_delta
```

## Why This Shape

This keeps the product honest:

- no hidden business-rule guessing
- no noisy AI assertions about domain behavior
- no findings unless the repository declares what matters

The next implementation step is enforcing additional declared invariant sections after this first critical-flow rule proves useful.
