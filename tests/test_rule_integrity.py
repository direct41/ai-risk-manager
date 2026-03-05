from __future__ import annotations

from ai_risk_manager.rules.engine import run_rules
from ai_risk_manager.signals.types import CapabilitySignal, SignalBundle


def test_write_contract_integrity_reports_db_insert_binding_mismatch() -> None:
    findings = run_rules(
        SignalBundle(
            signals=[
                CapabilitySignal(
                    id="sig-insert-mismatch",
                    kind="write_contract_integrity",
                    source_ref="server/services/notesService.js:92",
                    confidence="high",
                    evidence_refs=["server/services/notesService.js:92"],
                    attributes={
                        "issue_type": "db_insert_binding_mismatch",
                        "owner_name": "createNote",
                        "column": "title",
                        "value_field": "content",
                    },
                )
            ],
            supported_kinds={"write_contract_integrity"},
        )
    )
    rule_ids = {row.rule_id for row in findings.findings}
    assert "db_insert_binding_mismatch" in rule_ids


def test_write_contract_integrity_reports_write_scope_and_stale_write_issues() -> None:
    findings = run_rules(
        SignalBundle(
            signals=[
                CapabilitySignal(
                    id="sig-write-scope",
                    kind="write_contract_integrity",
                    source_ref="server/services/notesService.js:172",
                    confidence="high",
                    evidence_refs=["server/services/notesService.js:172"],
                    attributes={
                        "issue_type": "write_scope_missing_entity_filter",
                        "owner_name": "archiveNote",
                        "missing_filter": "id",
                    },
                ),
                CapabilitySignal(
                    id="sig-stale-write",
                    kind="write_contract_integrity",
                    source_ref="server/services/notesService.js:189",
                    confidence="medium",
                    evidence_refs=["server/services/notesService.js:189"],
                    attributes={
                        "issue_type": "stale_write_without_conflict_guard",
                        "owner_name": "autosaveNote",
                    },
                ),
            ],
            supported_kinds={"write_contract_integrity"},
        )
    )
    rule_ids = {row.rule_id for row in findings.findings}
    assert "critical_write_scope_missing_entity_filter" in rule_ids
    assert "stale_write_without_conflict_guard" in rule_ids


def test_session_lifecycle_consistency_reports_storage_key_mismatch() -> None:
    findings = run_rules(
        SignalBundle(
            signals=[
                CapabilitySignal(
                    id="sig-session-key",
                    kind="session_lifecycle_consistency",
                    source_ref="public/app.js:214",
                    confidence="high",
                    evidence_refs=["public/app.js:214"],
                    attributes={
                        "issue_type": "storage_key_mismatch",
                        "owner_name": "localStorage",
                        "set_key": "sessionToken",
                        "remove_key": "session_token",
                    },
                )
            ],
            supported_kinds={"session_lifecycle_consistency"},
        )
    )
    assert any(row.rule_id == "session_token_key_mismatch" for row in findings.findings)


def test_html_render_safety_reports_unsafe_innerhtml_sink() -> None:
    findings = run_rules(
        SignalBundle(
            signals=[
                CapabilitySignal(
                    id="sig-innerhtml",
                    kind="html_render_safety",
                    source_ref="public/app.js:87",
                    confidence="high",
                    evidence_refs=["public/app.js:87"],
                    attributes={
                        "issue_type": "unsanitized_innerhtml",
                        "owner_name": "renderNotes",
                        "sink": "refs.notesContainer.innerHTML",
                    },
                )
            ],
            supported_kinds={"html_render_safety"},
        )
    )
    assert any(row.rule_id == "stored_xss_unsafe_innerhtml" for row in findings.findings)


def test_write_contract_integrity_reports_note_math_unit_logic_risks() -> None:
    findings = run_rules(
        SignalBundle(
            signals=[
                CapabilitySignal(
                    id="sig-reading-round",
                    kind="write_contract_integrity",
                    source_ref="server/utils/noteMath.js:8",
                    confidence="medium",
                    evidence_refs=["server/utils/noteMath.js:8"],
                    attributes={
                        "issue_type": "reading_time_rounding_floor_missing",
                        "owner_name": "calculateReadingMinutes",
                        "divisor": "220",
                    },
                ),
                CapabilitySignal(
                    id="sig-priority-ternary",
                    kind="write_contract_integrity",
                    source_ref="server/utils/noteMath.js:23",
                    confidence="medium",
                    evidence_refs=["server/utils/noteMath.js:23"],
                    attributes={
                        "issue_type": "priority_ternary_constant_branch",
                        "owner_name": "calculatePriorityScore",
                        "flag_name": "pinned",
                    },
                ),
                CapabilitySignal(
                    id="sig-date-compare",
                    kind="write_contract_integrity",
                    source_ref="server/utils/noteMath.js:16",
                    confidence="high",
                    evidence_refs=["server/utils/noteMath.js:16"],
                    attributes={
                        "issue_type": "date_string_compare_with_iso",
                        "owner_name": "isOverdue",
                        "compared_value": "dueDate",
                    },
                ),
            ],
            supported_kinds={"write_contract_integrity"},
        )
    )
    rule_ids = {row.rule_id for row in findings.findings}
    assert "reading_time_round_down_to_zero" in rule_ids
    assert "priority_formula_precedence_risk" in rule_ids
    assert "overdue_date_string_comparison" in rule_ids


def test_ui_ergonomics_reports_pagination_save_and_mobile_layout_issues() -> None:
    findings = run_rules(
        SignalBundle(
            signals=[
                CapabilitySignal(
                    id="sig-pagination",
                    kind="ui_ergonomics",
                    source_ref="public/app.js:114",
                    confidence="medium",
                    evidence_refs=["public/app.js:114"],
                    attributes={
                        "issue_type": "pagination_page_not_normalized_after_mutation",
                        "owner_name": "loadNotes",
                    },
                ),
                CapabilitySignal(
                    id="sig-save",
                    kind="ui_ergonomics",
                    source_ref="public/app.js:146",
                    confidence="medium",
                    evidence_refs=["public/app.js:146"],
                    attributes={
                        "issue_type": "save_button_partial_form_enabled",
                        "owner_name": "updateSaveButtonState",
                        "condition": "title || content",
                    },
                ),
                CapabilitySignal(
                    id="sig-mobile",
                    kind="ui_ergonomics",
                    source_ref="public/styles.css:25",
                    confidence="medium",
                    evidence_refs=["public/styles.css:25"],
                    attributes={
                        "issue_type": "mobile_layout_min_width_overflow",
                        "owner_name": ".app",
                        "min_width_px": "980",
                    },
                ),
            ],
            supported_kinds={"ui_ergonomics"},
        )
    )
    rule_ids = {row.rule_id for row in findings.findings}
    assert "pagination_page_not_normalized" in rule_ids
    assert "save_button_partial_form_enabled" in rule_ids
    assert "mobile_layout_min_width_overflow" in rule_ids
