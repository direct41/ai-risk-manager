from __future__ import annotations

GRAPH_FIRST_RULE_IDS = frozenset(
    {
        "broken_invariant_on_transition",
        "critical_flow_no_integration_tests",
        "critical_path_no_tests",
        "dependency_risk_policy_violation",
        "missing_transition_handler",
    }
)

# Compatibility inventory. New generic risk rules must consume the canonical graph instead.
FROZEN_SIGNAL_ONLY_RULE_IDS = frozenset(
    {
        "agent_generated_test_missing_negative_path",
        "agent_generated_test_nondeterministic_dependency",
        "business_critical_flow_changed_without_check_delta",
        "critical_write_missing_authz",
        "critical_write_scope_missing_entity_filter",
        "db_insert_binding_mismatch",
        "input_normalization_char_split",
        "lossy_decode_error_handling",
        "missing_required_side_effect",
        "mobile_layout_min_width_overflow",
        "overdue_date_string_comparison",
        "pagination_page_not_normalized",
        "pr_admin_surface_change_requires_review",
        "pr_auth_boundary_change_requires_review",
        "pr_code_change_without_test_delta",
        "pr_contract_change_without_test_delta",
        "pr_dependency_change_without_test_delta",
        "pr_documented_mapping_key_renamed_without_docs",
        "pr_dynamic_gettext_message",
        "pr_migration_change_without_test_delta",
        "pr_new_4xx_branch_without_negative_test_delta",
        "pr_payment_boundary_change_requires_review",
        "pr_query_array_limit_without_indexed_compat_test",
        "pr_runtime_config_change_requires_review",
        "pr_strict_field_datetime_parse_without_empty_test",
        "pr_workflow_change_requires_review",
        "priority_formula_precedence_risk",
        "reading_time_round_down_to_zero",
        "response_field_contract_mismatch",
        "save_button_partial_form_enabled",
        "session_token_key_mismatch",
        "stale_write_without_conflict_guard",
        "stored_xss_unsafe_innerhtml",
        "ui_journey_smoke_failed",
        "unique_constraint_constant_create_default",
        "workflow_external_action_not_pinned",
        "workflow_untrusted_context_to_shell",
    }
)


__all__ = ["FROZEN_SIGNAL_ONLY_RULE_IDS", "GRAPH_FIRST_RULE_IDS"]
