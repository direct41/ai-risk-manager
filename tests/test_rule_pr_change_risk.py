from __future__ import annotations

from pathlib import Path

from ai_risk_manager.pipeline.pr_change_signals import build_pr_change_signal_bundle, build_pr_diff_signal_bundle
from ai_risk_manager.rules.engine import run_rules


def test_pr_change_signals_flag_code_delta_without_tests() -> None:
    signals = build_pr_change_signal_bundle({"src/service.py", "src/api.py"})

    findings = run_rules(signals)

    assert any(row.rule_id == "pr_code_change_without_test_delta" for row in findings.findings)


def test_pr_change_signals_skip_code_delta_when_tests_changed() -> None:
    signals = build_pr_change_signal_bundle({"src/service.py", "tests/test_service.py"})

    findings = run_rules(signals)

    assert not any(row.rule_id == "pr_code_change_without_test_delta" for row in findings.findings)


def test_pr_change_signals_skip_exact_equivalent_js_alias_rewrite(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"engines": {"node": ">= 18"}}\n',
        encoding="utf-8",
    )
    diff = (
        "diff --git a/lib/request.js b/lib/request.js\n"
        "--- a/lib/request.js\n"
        "+++ b/lib/request.js\n"
        "@@ -1 +1 @@\n"
        "-const value = header.trimRight()\n"
        "+const value = header.trimEnd()\n"
    )

    signals = build_pr_change_signal_bundle({"lib/request.js"}, diff, tmp_path)
    findings = run_rules(signals)

    assert not any(row.rule_id == "pr_code_change_without_test_delta" for row in findings.findings)


def test_pr_change_signals_keep_mixed_js_alias_rewrite() -> None:
    diff = (
        "diff --git a/lib/request.js b/lib/request.js\n"
        "--- a/lib/request.js\n"
        "+++ b/lib/request.js\n"
        "@@ -1 +1 @@\n"
        "-const value = header.substring(0, header.indexOf(',')).trimRight()\n"
        "+const value = header.split(',', 1)[0].trimEnd();\n"
    )

    signals = build_pr_change_signal_bundle({"lib/request.js"}, diff)
    findings = run_rules(signals)

    assert any(row.rule_id == "pr_code_change_without_test_delta" for row in findings.findings)


def test_pr_change_signals_keep_alias_rewrite_without_supported_runtime(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"engines": {"node": ">= 8"}}\n',
        encoding="utf-8",
    )
    diff = (
        "diff --git a/lib/request.js b/lib/request.js\n"
        "--- a/lib/request.js\n"
        "+++ b/lib/request.js\n"
        "@@ -1 +1 @@\n"
        "-const value = header.trimRight()\n"
        "+const value = header.trimEnd()\n"
    )

    signals = build_pr_change_signal_bundle({"lib/request.js"}, diff, tmp_path)
    findings = run_rules(signals)

    assert any(row.rule_id == "pr_code_change_without_test_delta" for row in findings.findings)


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


def test_pr_diff_signals_flag_documented_mapping_key_rename(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "renderers.md").write_text("Templates receive the `details` key.\n", encoding="utf-8")
    diff = (
        "diff --git a/rest_framework/renderers.py b/rest_framework/renderers.py\n"
        "--- a/rest_framework/renderers.py\n"
        "+++ b/rest_framework/renderers.py\n"
        "@@ -171 +171 @@\n"
        "-            return {'details': data, 'status_code': response.status_code}\n"
        "+            return {'results': data, 'status_code': response.status_code}\n"
    )

    signals = build_pr_diff_signal_bundle(
        tmp_path,
        diff,
        {"rest_framework/renderers.py", "tests/test_htmlrenderer.py"},
    )
    findings = run_rules(signals)

    finding = next(row for row in findings.findings if row.rule_id == "pr_documented_mapping_key_renamed_without_docs")
    assert finding.severity == "high"
    assert "deprecation" in finding.recommendation
    assert "docs/renderers.md" in finding.evidence_refs


def test_pr_diff_signals_skip_mapping_key_rename_when_docs_change(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "renderers.md").write_text("Templates receive the `details` key.\n", encoding="utf-8")
    diff = (
        "diff --git a/app/renderers.py b/app/renderers.py\n"
        "--- a/app/renderers.py\n"
        "+++ b/app/renderers.py\n"
        "@@ -1 +1 @@\n"
        "-CONTEXT = {'details': []}\n"
        "+CONTEXT = {'results': []}\n"
    )

    signals = build_pr_diff_signal_bundle(
        tmp_path,
        diff,
        {"app/renderers.py", "docs/renderers.md"},
    )

    assert signals.signals == []


def test_pr_diff_signals_ignore_documentation_in_dependency_trees(tmp_path: Path) -> None:
    dependency_docs = tmp_path / ".venv" / "lib" / "package"
    dependency_docs.mkdir(parents=True)
    (dependency_docs / "README.md").write_text("Use the `details` key.\n", encoding="utf-8")
    diff = (
        "diff --git a/app/renderers.py b/app/renderers.py\n"
        "--- a/app/renderers.py\n"
        "+++ b/app/renderers.py\n"
        "@@ -1 +1 @@\n"
        "-CONTEXT = {'details': []}\n"
        "+CONTEXT = {'results': []}\n"
    )

    signals = build_pr_diff_signal_bundle(tmp_path, diff, {"app/renderers.py"})

    assert signals.signals == []


def test_pr_diff_signals_flag_new_4xx_branch_without_negative_test(tmp_path: Path) -> None:
    diff = (
        "diff --git a/app/api.py b/app/api.py\n"
        "--- a/app/api.py\n"
        "+++ b/app/api.py\n"
        "@@ -10,0 +11,5 @@\n"
        "+    if existing:\n"
        "+        raise HTTPException(\n"
        "+            status_code=400,\n"
        "+            detail='Already exists',\n"
        "+        )\n"
        "diff --git a/tests/test_api.py b/tests/test_api.py\n"
        "--- a/tests/test_api.py\n"
        "+++ b/tests/test_api.py\n"
        "@@ -20 +20 @@\n"
        "-    assert response.status_code == 200\n"
        "+    assert response.status_code == 201\n"
    )

    signals = build_pr_diff_signal_bundle(tmp_path, diff, {"app/api.py", "tests/test_api.py"})
    findings = run_rules(signals)

    finding = next(row for row in findings.findings if row.rule_id == "pr_new_4xx_branch_without_negative_test_delta")
    assert finding.severity == "high"
    assert "status code" in finding.recommendation


def test_pr_diff_signals_accept_new_4xx_branch_with_negative_test(tmp_path: Path) -> None:
    diff = (
        "diff --git a/app/api.py b/app/api.py\n"
        "--- a/app/api.py\n"
        "+++ b/app/api.py\n"
        "@@ -10,0 +11,2 @@\n"
        "+    if existing:\n"
        "+        raise HTTPException(status_code=409, detail='Already exists')\n"
        "diff --git a/tests/test_api.py b/tests/test_api.py\n"
        "--- a/tests/test_api.py\n"
        "+++ b/tests/test_api.py\n"
        "@@ -20,0 +21,2 @@\n"
        "+    response = client.post('/users', json=duplicate)\n"
        "+    assert response.status_code == 409\n"
    )

    signals = build_pr_diff_signal_bundle(tmp_path, diff, {"app/api.py", "tests/test_api.py"})

    assert not any(
        signal.attributes.get("issue_type") == "new_4xx_branch_without_negative_test_delta"
        for signal in signals.signals
    )


def test_pr_diff_signals_flag_dynamic_gettext_messages(tmp_path: Path) -> None:
    source = tmp_path / "app" / "messages.py"
    source.parent.mkdir()
    source.write_text(
        "from django.utils.translation import gettext_lazy as _\n"
        "\n"
        "def messages(field_name):\n"
        "    label = _(field_name.title())\n"
        "    error = _(f'Must include {field_name}.')\n"
        "    return label, error\n",
        encoding="utf-8",
    )
    diff = (
        "diff --git a/app/messages.py b/app/messages.py\n"
        "--- a/app/messages.py\n"
        "+++ b/app/messages.py\n"
        "@@ -1,3 +1,6 @@\n"
        " from django.utils.translation import gettext_lazy as _\n"
        " \n"
        " def messages(field_name):\n"
        "+    label = _(field_name.title())\n"
        "+    error = _(f'Must include {field_name}.')\n"
        "+    return label, error\n"
    )

    signals = build_pr_diff_signal_bundle(tmp_path, diff, {"app/messages.py"})
    findings = run_rules(signals)

    finding = next(row for row in findings.findings if row.rule_id == "pr_dynamic_gettext_message")
    assert finding.severity == "medium"
    assert "named placeholders" in finding.recommendation
    assert "line(s) 4, 5" in finding.evidence


def test_pr_diff_signals_accept_literal_gettext_message(tmp_path: Path) -> None:
    source = tmp_path / "app" / "messages.py"
    source.parent.mkdir()
    source.write_text(
        "from django.utils.translation import gettext as _\n"
        "\n"
        "def message(field_name):\n"
        "    return _('Must include %(field_name)s.') % {'field_name': field_name}\n",
        encoding="utf-8",
    )
    diff = (
        "diff --git a/app/messages.py b/app/messages.py\n"
        "--- a/app/messages.py\n"
        "+++ b/app/messages.py\n"
        "@@ -1,3 +1,4 @@\n"
        " from django.utils.translation import gettext as _\n"
        " \n"
        " def message(field_name):\n"
        "+    return _('Must include %(field_name)s.') % {'field_name': field_name}\n"
    )

    signals = build_pr_diff_signal_bundle(tmp_path, diff, {"app/messages.py"})

    assert not any(signal.attributes.get("issue_type") == "dynamic_gettext_message" for signal in signals.signals)
