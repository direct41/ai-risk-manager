from __future__ import annotations

from typing import cast

from ai_risk_manager.graph.builder import build_graph
from ai_risk_manager.signals.types import SignalBundle
from ai_risk_manager.schemas.types import Confidence, Finding, FindingsReport, Graph, RiskPolicy, Severity

DEPENDENCY_VIOLATIONS_BY_POLICY: dict[RiskPolicy, set[str]] = {
    "conservative": {"direct_reference", "wildcard_version"},
    "balanced": {"direct_reference", "wildcard_version", "range_not_pinned"},
    "aggressive": {"direct_reference", "wildcard_version", "range_not_pinned", "unpinned_version"},
}
DEPENDENCY_SEVERITY_BY_SCOPE: dict[str, dict[str, str]] = {
    "runtime": {
        "direct_reference": "high",
        "wildcard_version": "high",
        "range_not_pinned": "medium",
        "unpinned_version": "medium",
    },
    "development": {
        "direct_reference": "medium",
        "wildcard_version": "medium",
        "range_not_pinned": "low",
        "unpinned_version": "low",
    },
}


def _run_rules_on_graph(graph: Graph, *, risk_policy: RiskPolicy = "balanced") -> FindingsReport:
    findings: list[Finding] = []
    api_nodes = [n for n in graph.nodes if n.type == "API"]
    dependency_nodes = [n for n in graph.nodes if n.type == "Dependency"]
    covered_api_ids = {e.target_node_id for e in graph.edges if e.type == "covered_by"}

    for api in api_nodes:
        if api.id not in covered_api_ids:
            finding_id = f"critical_path_no_tests:{api.id}"
            findings.append(
                Finding(
                    id=finding_id,
                    rule_id="critical_path_no_tests",
                    title=f"Write endpoint '{api.name}' has no matching tests",
                    description="Critical path endpoint appears uncovered by tests in current graph.",
                    severity="high",
                    confidence="medium",
                    evidence=f"No covered_by edge found for {api.id}",
                    source_ref=api.source_ref,
                    suppression_key=f"{finding_id}",
                    recommendation=f"Add API/service tests for endpoint '{api.name}', including success and error paths.",
                    origin="deterministic",
                    evidence_refs=[api.source_ref],
                    generated_without_llm=True,
                )
            )

    declared_pairs = {(t.source, t.target) for t in graph.declared_transitions}
    handled_pairs = {(t.source, t.target) for t in graph.handled_transitions}
    missing_pairs = declared_pairs - handled_pairs
    for source, target in sorted(missing_pairs):
        source_ref = next((t.source_ref for t in graph.declared_transitions if t.source == source and t.target == target), "unknown")
        finding_id = f"missing_transition_handler:{source}->{target}"
        findings.append(
                Finding(
                id=finding_id,
                rule_id="missing_transition_handler",
                title=f"Declared transition '{source} -> {target}' has no handler",
                description="A declared transition exists but no matching status-change handler was found.",
                severity="medium",
                confidence="medium",
                evidence=f"Declared transitions include {source}->{target}; handled transitions do not.",
                source_ref=source_ref,
                suppression_key=finding_id,
                recommendation=f"Implement handler logic for transition '{source} -> {target}' or remove stale declaration.",
                    origin="deterministic",
                    evidence_refs=[source_ref],
                    generated_without_llm=True,
                )
            )

    for transition in graph.handled_transitions:
        if transition.invariant_guarded:
            continue
        if (transition.source, transition.target) in declared_pairs:
            # Treat explicit transition declarations as a baseline invariant anchor.
            continue
        finding_id = f"broken_invariant_on_transition:{transition.machine}:{transition.source}->{transition.target}"
        findings.append(
                Finding(
                id=finding_id,
                rule_id="broken_invariant_on_transition",
                title=f"Transition '{transition.source} -> {transition.target}' lacks invariant guard",
                description=(
                    "State transition handler mutates status without explicit invariant/guard validation before write."
                ),
                severity="high",
                confidence="medium",
                evidence=(
                    f"Detected direct transition '{transition.source}->{transition.target}' in handler "
                    f"'{transition.machine}' without guard markers."
                ),
                source_ref=transition.source_ref,
                suppression_key=finding_id,
                recommendation=(
                    f"Add explicit guard checks for transition '{transition.source} -> {transition.target}' "
                    f"in handler '{transition.machine}' (assertions/validation/policy checks)."
                ),
                    origin="deterministic",
                    evidence_refs=[transition.source_ref],
                    generated_without_llm=True,
                )
            )

    for dep in dependency_nodes:
        violation = str(dep.details.get("policy_violation") or "").strip()
        if not violation:
            continue
        if violation not in DEPENDENCY_VIOLATIONS_BY_POLICY[risk_policy]:
            continue
        scope = str(dep.details.get("scope") or "runtime").strip().lower() or "runtime"
        severity_map = DEPENDENCY_SEVERITY_BY_SCOPE.get(scope, DEPENDENCY_SEVERITY_BY_SCOPE["runtime"])
        spec = str(dep.details.get("spec") or "").strip()
        if violation == "direct_reference":
            recommendation = (
                f"Replace direct reference for dependency '{dep.name}' with a pinned package version (==) "
                "from a trusted index."
            )
        elif violation == "wildcard_version":
            recommendation = f"Replace wildcard pin for dependency '{dep.name}' with an exact version (==)."
        elif violation == "range_not_pinned":
            recommendation = f"Pin dependency '{dep.name}' to an exact version (==) and update via controlled bumps."
        else:
            recommendation = f"Specify an exact version (==) for dependency '{dep.name}'."

        finding_id = f"dependency_risk_policy_violation:{dep.id}"
        findings.append(
                Finding(
                id=finding_id,
                rule_id="dependency_risk_policy_violation",
                title=f"Dependency '{dep.name}' violates version policy ({violation})",
                description=(
                    "Dependency specification is not pinned to an immutable version and may increase supply-chain risk."
                ),
                severity=cast(Severity, severity_map.get(violation, "medium")),
                confidence="high",
                evidence=f"Detected dependency spec '{spec or '(none)'}' at {dep.source_ref} (scope: {scope}).",
                source_ref=dep.source_ref,
                suppression_key=finding_id,
                recommendation=recommendation,
                    origin="deterministic",
                    evidence_refs=[dep.source_ref],
                    generated_without_llm=True,
                )
            )

    return FindingsReport(findings=findings, generated_without_llm=True)


def _run_signal_only_rules(signals: SignalBundle) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(_run_missing_required_side_effect_rule(signals))
    findings.extend(_run_critical_write_missing_authz_rule(signals))
    findings.extend(_run_write_contract_integrity_rule(signals))
    findings.extend(_run_session_lifecycle_consistency_rule(signals))
    findings.extend(_run_html_render_safety_rule(signals))
    findings.extend(_run_ui_ergonomics_rule(signals))
    findings.extend(_run_generated_test_quality_rule(signals))
    findings.extend(_run_workflow_automation_risk_rule(signals))
    return findings


def _run_missing_required_side_effect_rule(signals: SignalBundle) -> list[Finding]:
    findings: list[Finding] = []
    emitted_keys: set[tuple[str, str]] = set()
    required: list[tuple[str, str, str, str, str]] = []

    for signal in signals.signals:
        if signal.kind != "side_effect_emit_contract":
            continue
        role = str(signal.attributes.get("role", "")).strip()
        effect_kind = str(signal.attributes.get("effect_kind", "")).strip()
        effect_target = str(signal.attributes.get("effect_target", "")).strip()
        owner_name = str(signal.attributes.get("owner_name", "unknown")).strip() or "unknown"
        if not effect_kind or not effect_target:
            continue

        key = (effect_kind, effect_target)
        if role == "emitted":
            emitted_keys.add(key)
        elif role == "required":
            required.append((signal.source_ref, owner_name, effect_kind, effect_target, signal.id))

    for source_ref, owner_name, effect_kind, effect_target, signal_id in required:
        if (effect_kind, effect_target) in emitted_keys:
            continue
        finding_id = f"missing_required_side_effect:{owner_name}:{effect_kind}:{effect_target}:{signal_id}"
        findings.append(
            Finding(
                id=finding_id,
                rule_id="missing_required_side_effect",
                title=f"Missing required side-effect '{effect_kind}:{effect_target}' for '{owner_name}'",
                description=(
                    "A required side-effect contract was declared but no matching emitted side-effect signal was found."
                ),
                severity="high",
                confidence="medium",
                evidence=(
                    f"Required side-effect '{effect_kind}:{effect_target}' declared for '{owner_name}' "
                    "without matching emitted side-effect evidence."
                ),
                source_ref=source_ref,
                suppression_key=finding_id,
                recommendation=(
                    f"Ensure '{owner_name}' emits side-effect '{effect_kind}:{effect_target}' "
                    "or update the declared side-effect contract."
                ),
                origin="deterministic",
                evidence_refs=[source_ref],
                generated_without_llm=True,
            )
        )

    return findings


def _run_critical_write_missing_authz_rule(signals: SignalBundle) -> list[Finding]:
    if "authorization_boundary_enforced" not in signals.supported_kinds:
        return []

    findings: list[Finding] = []
    protected_owners: set[str] = set()
    for signal in signals.signals:
        if signal.kind != "authorization_boundary_enforced":
            continue
        owner_name = str(signal.attributes.get("owner_name", "")).strip()
        if owner_name:
            protected_owners.add(owner_name)

    for signal in signals.signals:
        if signal.kind != "http_write_surface":
            continue
        owner_name = str(signal.attributes.get("endpoint_name", "")).strip()
        if not owner_name:
            continue
        if owner_name in protected_owners:
            continue

        method = str(signal.attributes.get("method", "")).strip().upper()
        path = str(signal.attributes.get("path", "")).strip()
        finding_id = f"critical_write_missing_authz:{owner_name}:{method}:{path}:{signal.id}"
        findings.append(
            Finding(
                id=finding_id,
                rule_id="critical_write_missing_authz",
                title=f"Critical write endpoint '{owner_name}' lacks authz boundary",
                description=(
                    "Write endpoint is part of a stack with declared authorization signal support, "
                    "but no authorization boundary evidence was found for this endpoint."
                ),
                severity="high",
                confidence="medium",
                evidence=(
                    f"Detected write endpoint '{owner_name}' ({method} {path}) "
                    "without matching authorization boundary signal."
                ),
                source_ref=signal.source_ref,
                suppression_key=finding_id,
                recommendation=(
                    f"Add and enforce authorization boundary for endpoint '{owner_name}' "
                    "(permission/policy/decorator/guard) and expose it as "
                    "`authorization_boundary_enforced` signal."
                ),
                origin="deterministic",
                evidence_refs=[signal.source_ref],
                generated_without_llm=True,
            )
        )

    return findings


def _run_write_contract_integrity_rule(signals: SignalBundle) -> list[Finding]:
    findings: list[Finding] = []
    for signal in signals.signals:
        if signal.kind != "write_contract_integrity":
            continue

        issue_type = str(signal.attributes.get("issue_type", "")).strip()
        owner_name = str(signal.attributes.get("owner_name", "")).strip() or "unknown"
        snippet = str(signal.attributes.get("snippet", "")).strip()
        confidence = cast(Confidence, signal.confidence)

        if issue_type == "char_split_normalization":
            field_name = str(signal.attributes.get("field_name", "")).strip() or "unknown"
            finding_id = f"input_normalization_char_split:{owner_name}:{field_name}:{signal.id}"
            findings.append(
                Finding(
                    id=finding_id,
                    rule_id="input_normalization_char_split",
                    title=f"Suspicious char-split normalization for field '{field_name}'",
                    description=(
                        "Detected request-field normalization that splits input into characters before persistence, "
                        "which can corrupt list-like payload semantics."
                    ),
                    severity="medium",
                    confidence=confidence,
                    evidence=(
                        f"Owner '{owner_name}' normalizes field '{field_name}' via character split "
                        f"(evidence snippet: {snippet or 'n/a'})."
                    ),
                    source_ref=signal.source_ref,
                    suppression_key=finding_id,
                    recommendation=(
                        f"Replace character-level split normalization for '{field_name}' with delimiter-aware parsing "
                        "(for example CSV split/trim) or require array input at the boundary."
                    ),
                    origin="deterministic",
                    evidence_refs=[signal.source_ref],
                    generated_without_llm=True,
                )
            )
            continue

        if issue_type == "response_field_alias_mismatch":
            consumer_field = str(signal.attributes.get("consumer_field", "")).strip() or "unknown"
            producer_field = str(signal.attributes.get("producer_field", "")).strip() or "unknown"
            finding_id = f"response_field_contract_mismatch:{owner_name}:{consumer_field}:{producer_field}:{signal.id}"
            findings.append(
                Finding(
                    id=finding_id,
                    rule_id="response_field_contract_mismatch",
                    title=f"Response field contract mismatch for '{consumer_field}'",
                    description=(
                        "Consumer code references a response field that does not match producer field naming, "
                        "which can silently break UI state rendering."
                    ),
                    severity="medium",
                    confidence=confidence,
                    evidence=(
                        f"Consumer expects '{consumer_field}' while producer exposes '{producer_field}' "
                        f"(owner: '{owner_name}')."
                    ),
                    source_ref=signal.source_ref,
                    suppression_key=finding_id,
                    recommendation=(
                        f"Align producer/consumer field contract for '{consumer_field}' (or add explicit mapping) "
                        "to avoid stale or incorrect UI state."
                    ),
                    origin="deterministic",
                    evidence_refs=[signal.source_ref],
                    generated_without_llm=True,
                )
            )
            continue

        if issue_type == "db_insert_binding_mismatch":
            column = str(signal.attributes.get("column", "")).strip() or "unknown"
            value_field = str(signal.attributes.get("value_field", "")).strip() or "unknown"
            finding_id = f"db_insert_binding_mismatch:{owner_name}:{column}:{value_field}:{signal.id}"
            findings.append(
                Finding(
                    id=finding_id,
                    rule_id="db_insert_binding_mismatch",
                    title=f"DB insert binding mismatch for column '{column}'",
                    description=(
                        "Insert value bindings appear to map a request field to a different target column, "
                        "which can persist swapped or corrupted data."
                    ),
                    severity="high",
                    confidence=confidence,
                    evidence=(
                        f"Owner '{owner_name}' binds field '{value_field}' into column '{column}'."
                    ),
                    source_ref=signal.source_ref,
                    suppression_key=finding_id,
                    recommendation=(
                        f"Align insert binding order for column '{column}' with its corresponding request/domain field."
                    ),
                    origin="deterministic",
                    evidence_refs=[signal.source_ref],
                    generated_without_llm=True,
                )
            )
            continue

        if issue_type == "write_scope_missing_entity_filter":
            missing_filter = str(signal.attributes.get("missing_filter", "")).strip() or "entity id"
            finding_id = f"critical_write_scope_missing_entity_filter:{owner_name}:{missing_filter}:{signal.id}"
            findings.append(
                Finding(
                    id=finding_id,
                    rule_id="critical_write_scope_missing_entity_filter",
                    title=f"Critical write scope may be too broad in '{owner_name}'",
                    description=(
                        "A write query updates/deletes data without expected entity-level filter, "
                        "which can impact multiple records unintentionally."
                    ),
                    severity="high",
                    confidence=confidence,
                    evidence=(
                        f"Owner '{owner_name}' issues a critical write without '{missing_filter}' guard."
                    ),
                    source_ref=signal.source_ref,
                    suppression_key=finding_id,
                    recommendation=(
                        f"Add entity-level filter ('{missing_filter}') to write scope and keep tenant/user guard in place."
                    ),
                    origin="deterministic",
                    evidence_refs=[signal.source_ref],
                    generated_without_llm=True,
                )
            )
            continue

        if issue_type == "stale_write_without_conflict_guard":
            finding_id = f"stale_write_without_conflict_guard:{owner_name}:{signal.id}"
            findings.append(
                Finding(
                    id=finding_id,
                    rule_id="stale_write_without_conflict_guard",
                    title=f"Potential stale write without conflict guard in '{owner_name}'",
                    description=(
                        "Write path applies client-sourced freshness data without compare-and-set/version check, "
                        "which can overwrite newer updates."
                    ),
                    severity="high",
                    confidence=confidence,
                    evidence=(
                        f"Owner '{owner_name}' updates mutable content with client freshness token "
                        "but query predicate lacks version/updated_at guard."
                    ),
                    source_ref=signal.source_ref,
                    suppression_key=finding_id,
                    recommendation=(
                        "Use optimistic concurrency control (version/updated_at compare-and-set) and reject stale writes."
                    ),
                    origin="deterministic",
                    evidence_refs=[signal.source_ref],
                    generated_without_llm=True,
                )
            )
            continue

        if issue_type == "reading_time_rounding_floor_missing":
            divisor = str(signal.attributes.get("divisor", "")).strip() or "unknown"
            finding_id = f"reading_time_round_down_to_zero:{owner_name}:{divisor}:{signal.id}"
            findings.append(
                Finding(
                    id=finding_id,
                    rule_id="reading_time_round_down_to_zero",
                    title=f"Reading-time calculation may round short content to zero in '{owner_name}'",
                    description=(
                        "Detected reading-time computation using `Math.round(words/divisor)` without minimum floor, "
                        "which can produce zero minutes for short but non-empty content."
                    ),
                    severity="medium",
                    confidence=confidence,
                    evidence=(
                        f"Owner '{owner_name}' uses round-based reading-time expression with divisor '{divisor}'."
                    ),
                    source_ref=signal.source_ref,
                    suppression_key=finding_id,
                    recommendation=(
                        "Apply minimum floor for non-empty content (for example `Math.max(1, Math.ceil(...))`)."
                    ),
                    origin="deterministic",
                    evidence_refs=[signal.source_ref],
                    generated_without_llm=True,
                )
            )
            continue

        if issue_type == "priority_ternary_constant_branch":
            flag_name = str(signal.attributes.get("flag_name", "")).strip() or "flag"
            finding_id = f"priority_formula_precedence_risk:{owner_name}:{flag_name}:{signal.id}"
            findings.append(
                Finding(
                    id=finding_id,
                    rule_id="priority_formula_precedence_risk",
                    title=f"Priority formula may bypass boost terms in '{owner_name}'",
                    description=(
                        "Detected ternary branch where one branch returns a constant while the other applies additive boosts, "
                        "which often indicates precedence/parenthesization mistakes in scoring logic."
                    ),
                    severity="medium",
                    confidence=confidence,
                    evidence=(
                        f"Owner '{owner_name}' computes priority with ternary on '{flag_name}' and asymmetric branch complexity."
                    ),
                    source_ref=signal.source_ref,
                    suppression_key=finding_id,
                    recommendation=(
                        "Recheck ternary grouping so pinned/base terms and boost terms are combined per intended formula."
                    ),
                    origin="deterministic",
                    evidence_refs=[signal.source_ref],
                    generated_without_llm=True,
                )
            )
            continue

        if issue_type == "date_string_compare_with_iso":
            compared_value = str(signal.attributes.get("compared_value", "")).strip() or "date value"
            finding_id = f"overdue_date_string_comparison:{owner_name}:{compared_value}:{signal.id}"
            findings.append(
                Finding(
                    id=finding_id,
                    rule_id="overdue_date_string_comparison",
                    title=f"Overdue/date check compares raw strings in '{owner_name}'",
                    description=(
                        "Detected date comparison against `new Date().toISOString()` using string operators, "
                        "which can produce timezone and format edge-case errors."
                    ),
                    severity="high",
                    confidence=confidence,
                    evidence=(
                        f"Owner '{owner_name}' compares '{compared_value}' directly with ISO timestamp string."
                    ),
                    source_ref=signal.source_ref,
                    suppression_key=finding_id,
                    recommendation=(
                        "Parse to `Date`/epoch before comparison and normalize timezone expectations at boundary."
                    ),
                    origin="deterministic",
                    evidence_refs=[signal.source_ref],
                    generated_without_llm=True,
                )
            )

    return findings


def _run_session_lifecycle_consistency_rule(signals: SignalBundle) -> list[Finding]:
    findings: list[Finding] = []
    for signal in signals.signals:
        if signal.kind != "session_lifecycle_consistency":
            continue

        issue_type = str(signal.attributes.get("issue_type", "")).strip()
        if issue_type != "storage_key_mismatch":
            continue

        owner_name = str(signal.attributes.get("owner_name", "")).strip() or "unknown"
        set_key = str(signal.attributes.get("set_key", "")).strip() or "unknown"
        remove_key = str(signal.attributes.get("remove_key", "")).strip() or "unknown"
        finding_id = f"session_token_key_mismatch:{owner_name}:{set_key}:{remove_key}:{signal.id}"
        findings.append(
            Finding(
                id=finding_id,
                rule_id="session_token_key_mismatch",
                title="Session token storage key mismatch between login and logout",
                description=(
                    "Token lifecycle uses inconsistent storage keys, which can leave active session state after logout."
                ),
                severity="high",
                confidence=cast(Confidence, signal.confidence),
                evidence=(
                    f"Owner '{owner_name}' stores token under '{set_key}' but clears '{remove_key}'."
                ),
                source_ref=signal.source_ref,
                suppression_key=finding_id,
                recommendation=(
                    "Unify login/get/logout token storage keys and verify post-logout actions require re-authentication."
                ),
                origin="deterministic",
                evidence_refs=[signal.source_ref],
                generated_without_llm=True,
            )
        )

    return findings


def _run_html_render_safety_rule(signals: SignalBundle) -> list[Finding]:
    findings: list[Finding] = []
    for signal in signals.signals:
        if signal.kind != "html_render_safety":
            continue

        issue_type = str(signal.attributes.get("issue_type", "")).strip()
        if issue_type != "unsanitized_innerhtml":
            continue

        owner_name = str(signal.attributes.get("owner_name", "")).strip() or "unknown"
        sink = str(signal.attributes.get("sink", "")).strip() or "innerHTML"
        finding_id = f"stored_xss_unsafe_innerhtml:{owner_name}:{sink}:{signal.id}"
        findings.append(
            Finding(
                id=finding_id,
                rule_id="stored_xss_unsafe_innerhtml",
                title=f"Potential stored XSS via unsafe HTML sink in '{owner_name}'",
                description=(
                    "Untrusted content appears to flow into an HTML sink without sanitization or safe-text rendering."
                ),
                severity="high",
                confidence=cast(Confidence, signal.confidence),
                evidence=(
                    f"Detected dynamic note content rendered through '{sink}' in '{owner_name}' without sanitization."
                ),
                source_ref=signal.source_ref,
                suppression_key=finding_id,
                recommendation=(
                    "Render untrusted fields with text-safe APIs (`textContent`) or sanitize HTML before assigning to sinks."
                ),
                origin="deterministic",
                evidence_refs=[signal.source_ref],
                generated_without_llm=True,
            )
        )

    return findings


def _run_ui_ergonomics_rule(signals: SignalBundle) -> list[Finding]:
    findings: list[Finding] = []
    for signal in signals.signals:
        if signal.kind != "ui_ergonomics":
            continue

        issue_type = str(signal.attributes.get("issue_type", "")).strip()
        owner_name = str(signal.attributes.get("owner_name", "")).strip() or "unknown"
        confidence = cast(Confidence, signal.confidence)

        if issue_type == "pagination_page_not_normalized_after_mutation":
            finding_id = f"pagination_page_not_normalized:{owner_name}:{signal.id}"
            findings.append(
                Finding(
                    id=finding_id,
                    rule_id="pagination_page_not_normalized",
                    title=f"Pagination page index may stay out of bounds in '{owner_name}'",
                    description=(
                        "Pagination flow updates/deletes data but does not normalize current page against new max page, "
                        "which can leave UI on empty page."
                    ),
                    severity="medium",
                    confidence=confidence,
                    evidence=(
                        f"Owner '{owner_name}' uses mutable pagination state without explicit post-mutation page normalization."
                    ),
                    source_ref=signal.source_ref,
                    suppression_key=finding_id,
                    recommendation=(
                        "After list mutations, clamp `state.page` to `maxPage` and reload when current page becomes empty."
                    ),
                    origin="deterministic",
                    evidence_refs=[signal.source_ref],
                    generated_without_llm=True,
                )
            )
            continue

        if issue_type == "save_button_partial_form_enabled":
            condition = str(signal.attributes.get("condition", "")).strip() or "title || content"
            finding_id = f"save_button_partial_form_enabled:{owner_name}:{signal.id}"
            findings.append(
                Finding(
                    id=finding_id,
                    rule_id="save_button_partial_form_enabled",
                    title="Save button can be enabled with partially filled form",
                    description=(
                        "Form submit gating appears to use OR-condition for required fields, "
                        "which can allow incomplete submissions."
                    ),
                    severity="low",
                    confidence=confidence,
                    evidence=(
                        f"Owner '{owner_name}' enables submit using condition '{condition}'."
                    ),
                    source_ref=signal.source_ref,
                    suppression_key=finding_id,
                    recommendation=(
                        "Use AND-condition for required fields and keep button disabled until all mandatory inputs are present."
                    ),
                    origin="deterministic",
                    evidence_refs=[signal.source_ref],
                    generated_without_llm=True,
                )
            )
            continue

        if issue_type == "mobile_layout_min_width_overflow":
            min_width_px = str(signal.attributes.get("min_width_px", "")).strip() or "unknown"
            finding_id = f"mobile_layout_min_width_overflow:{owner_name}:{min_width_px}:{signal.id}"
            findings.append(
                Finding(
                    id=finding_id,
                    rule_id="mobile_layout_min_width_overflow",
                    title="Fixed minimum width can force horizontal scroll on narrow screens",
                    description=(
                        "Layout container declares large fixed `min-width`, which can break mobile viewport fit."
                    ),
                    severity="medium",
                    confidence=confidence,
                    evidence=(
                        f"Owner '{owner_name}' sets `min-width: {min_width_px}px`."
                    ),
                    source_ref=signal.source_ref,
                    suppression_key=finding_id,
                    recommendation=(
                        "Remove large fixed min-width for main container or override it in mobile breakpoints."
                    ),
                    origin="deterministic",
                    evidence_refs=[signal.source_ref],
                    generated_without_llm=True,
                )
            )

    return findings


def _run_generated_test_quality_rule(signals: SignalBundle) -> list[Finding]:
    findings: list[Finding] = []
    for signal in signals.signals:
        if signal.kind != "generated_test_quality":
            continue

        issue_type = str(signal.attributes.get("issue_type", "")).strip()
        test_name = str(signal.attributes.get("test_name", "")).strip() or str(signal.attributes.get("owner_name", "")).strip() or "unknown"
        confidence = cast(Confidence, signal.confidence)

        if issue_type == "missing_negative_path":
            method = str(signal.attributes.get("method", "")).strip().upper() or "WRITE"
            path = str(signal.attributes.get("path", "")).strip()
            target = f"{method} {path}".strip() if path else method
            finding_id = f"agent_generated_test_missing_negative_path:{test_name}:{method}:{path}:{signal.id}"
            findings.append(
                Finding(
                    id=finding_id,
                    rule_id="agent_generated_test_missing_negative_path",
                    title=f"Write-path test '{test_name}' lacks negative-path assertions",
                    description=(
                        "Test covers a write path but only exercises the success path, "
                        "which is common in weak AI-generated tests and misses validation/auth/conflict failures."
                    ),
                    severity="high" if method in {"POST", "PUT", "PATCH", "DELETE"} else "medium",
                    confidence=confidence,
                    evidence=(
                        f"Test '{test_name}' calls '{target}' without any detected negative-path assertions."
                    ),
                    source_ref=signal.source_ref,
                    suppression_key=finding_id,
                    recommendation=(
                        f"Add negative-path coverage for '{target}' in '{test_name}' "
                        "(for example validation, unauthorized, forbidden, not-found, or conflict cases)."
                    ),
                    origin="deterministic",
                    evidence_refs=[signal.source_ref],
                    generated_without_llm=True,
                )
            )
            continue

        if issue_type == "nondeterministic_dependency":
            dependency_kinds = str(signal.attributes.get("dependency_kinds", "")).strip() or "time"
            finding_id = f"agent_generated_test_nondeterministic_dependency:{test_name}:{dependency_kinds}:{signal.id}"
            findings.append(
                Finding(
                    id=finding_id,
                    rule_id="agent_generated_test_nondeterministic_dependency",
                    title=f"Test '{test_name}' depends on nondeterministic runtime behavior",
                    description=(
                        "Test appears to depend on sleep, current time, randomness, or live network behavior, "
                        "which increases flakiness and is common in low-quality generated tests."
                    ),
                    severity="medium",
                    confidence=confidence,
                    evidence=(
                        f"Test '{test_name}' uses nondeterministic dependency kinds: {dependency_kinds}."
                    ),
                    source_ref=signal.source_ref,
                    suppression_key=finding_id,
                    recommendation=(
                        "Replace nondeterministic dependencies with mocks, fake clocks, fixtures, or deterministic stubs."
                    ),
                    origin="deterministic",
                    evidence_refs=[signal.source_ref],
                    generated_without_llm=True,
                )
            )

    return findings


def _run_workflow_automation_risk_rule(signals: SignalBundle) -> list[Finding]:
    findings: list[Finding] = []
    for signal in signals.signals:
        if signal.kind != "workflow_automation_risk":
            continue

        issue_type = str(signal.attributes.get("issue_type", "")).strip()
        owner_name = str(signal.attributes.get("owner_name", "")).strip() or "workflow step"
        confidence = cast(Confidence, signal.confidence)

        if issue_type == "untrusted_context_to_shell":
            context_ref = str(signal.attributes.get("context_ref", "")).strip() or "github.event.*"
            finding_id = f"workflow_untrusted_context_to_shell:{owner_name}:{context_ref}:{signal.id}"
            findings.append(
                Finding(
                    id=finding_id,
                    rule_id="workflow_untrusted_context_to_shell",
                    title=f"Workflow step '{owner_name}' interpolates untrusted event text into shell context",
                    description=(
                        "GitHub event text such as issue, PR, or comment body/title appears inside a shell run step, "
                        "which can enable prompt or command injection through repository automation."
                    ),
                    severity="high",
                    confidence=confidence,
                    evidence=(
                        f"Workflow step '{owner_name}' references '{context_ref}' inside a shell run block."
                    ),
                    source_ref=signal.source_ref,
                    suppression_key=finding_id,
                    recommendation=(
                        "Do not pass untrusted event text directly into shell commands. Sanitize it, treat it as data, "
                        "or move handling into a trusted script boundary with explicit escaping."
                    ),
                    origin="deterministic",
                    evidence_refs=[signal.source_ref],
                    generated_without_llm=True,
                )
            )
            continue

        if issue_type == "external_action_not_pinned":
            action_ref = str(signal.attributes.get("action_ref", "")).strip() or "external action"
            finding_id = f"workflow_external_action_not_pinned:{owner_name}:{action_ref}:{signal.id}"
            findings.append(
                Finding(
                    id=finding_id,
                    rule_id="workflow_external_action_not_pinned",
                    title=f"Workflow step '{owner_name}' uses an external action without commit pinning",
                    description=(
                        "Workflow references an external GitHub Action by mutable tag or branch instead of immutable commit SHA, "
                        "which increases supply-chain risk in automation."
                    ),
                    severity="medium",
                    confidence=confidence,
                    evidence=(
                        f"Workflow step '{owner_name}' uses mutable external action ref '{action_ref}'."
                    ),
                    source_ref=signal.source_ref,
                    suppression_key=finding_id,
                    recommendation=(
                        "Pin external GitHub Actions to a full commit SHA and update them via controlled review."
                    ),
                    origin="deterministic",
                    evidence_refs=[signal.source_ref],
                    generated_without_llm=True,
                )
            )

    return findings


def run_rules(graph: Graph | SignalBundle, *, risk_policy: RiskPolicy = "balanced") -> FindingsReport:
    if isinstance(graph, SignalBundle):
        graph_findings = _run_rules_on_graph(build_graph(graph), risk_policy=risk_policy)
        signal_findings = _run_signal_only_rules(graph)
        return FindingsReport(findings=[*graph_findings.findings, *signal_findings], generated_without_llm=True)
    return _run_rules_on_graph(graph, risk_policy=risk_policy)
