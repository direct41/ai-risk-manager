from __future__ import annotations

from ai_risk_manager.pipeline.pr_change_signals import build_pr_change_signal_bundle
from ai_risk_manager.rules.engine import run_rules


def test_pr_change_signals_flag_code_delta_without_tests() -> None:
    signals = build_pr_change_signal_bundle({"src/service.py", "src/api.py"})

    findings = run_rules(signals)

    assert any(row.rule_id == "pr_code_change_without_test_delta" for row in findings.findings)


def test_pr_change_signals_skip_code_delta_when_tests_changed() -> None:
    signals = build_pr_change_signal_bundle({"src/service.py", "tests/test_service.py"})

    findings = run_rules(signals)

    assert not any(row.rule_id == "pr_code_change_without_test_delta" for row in findings.findings)


def test_pr_change_signals_skip_low_signal_source_paths() -> None:
    signals = build_pr_change_signal_bundle({"scripts/reindex.py", "examples/demo.ts"})

    findings = run_rules(signals)

    assert not any(row.rule_id == "pr_code_change_without_test_delta" for row in findings.findings)


def test_pr_change_signals_flag_dependency_and_workflow_changes() -> None:
    signals = build_pr_change_signal_bundle({"package.json", ".github/workflows/ci.yml"})

    findings = run_rules(signals)
    rule_ids = {row.rule_id for row in findings.findings}

    assert "pr_dependency_change_without_test_delta" in rule_ids
    assert "pr_workflow_change_requires_review" in rule_ids


def test_pr_change_signals_flag_contract_migration_and_runtime_config_changes() -> None:
    signals = build_pr_change_signal_bundle(
        {
            "openapi.yaml",
            "alembic/versions/20260414_add_orders.py",
            "Dockerfile",
            "infra/main.tf",
        }
    )

    findings = run_rules(signals)
    rule_ids = {row.rule_id for row in findings.findings}

    assert "pr_contract_change_without_test_delta" in rule_ids
    assert "pr_migration_change_without_test_delta" in rule_ids
    assert "pr_runtime_config_change_requires_review" in rule_ids


def test_pr_change_signals_skip_contract_and_migration_rules_when_tests_changed() -> None:
    signals = build_pr_change_signal_bundle(
        {
            "schema.graphql",
            "db/migrate/20260414_add_orders.sql",
            "tests/test_orders.py",
        }
    )

    findings = run_rules(signals)
    rule_ids = {row.rule_id for row in findings.findings}

    assert "pr_contract_change_without_test_delta" not in rule_ids
    assert "pr_migration_change_without_test_delta" not in rule_ids


def test_pr_change_signals_flag_sensitive_auth_payment_and_admin_paths() -> None:
    signals = build_pr_change_signal_bundle(
        {
            "src/auth/session_service.py",
            "src/billing/refund_handler.py",
            "src/admin/user_moderation.py",
        }
    )

    findings = run_rules(signals)
    rule_ids = {row.rule_id for row in findings.findings}

    assert "pr_auth_boundary_change_requires_review" in rule_ids
    assert "pr_payment_boundary_change_requires_review" in rule_ids
    assert "pr_admin_surface_change_requires_review" in rule_ids
    assert "pr_code_change_without_test_delta" not in rule_ids


def test_pr_change_signals_sensitive_paths_downgrade_when_tests_changed() -> None:
    signals = build_pr_change_signal_bundle(
        {
            "src/auth/session_service.py",
            "tests/test_auth_session.py",
        }
    )

    findings = run_rules(signals)
    auth = next(row for row in findings.findings if row.rule_id == "pr_auth_boundary_change_requires_review")

    assert auth.severity == "low"
