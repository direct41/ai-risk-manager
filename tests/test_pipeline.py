from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from ai_risk_manager.cli import main
from ai_risk_manager.pipeline.run import _resolve_effective_ci_mode, run_pipeline
from ai_risk_manager.schemas.types import Finding, FindingsReport, RunContext
from ai_risk_manager.stacks.discovery import StackDetectionResult


def test_preflight_fail_for_non_fastapi(tmp_path: Path, write_file) -> None:
    write_file(tmp_path / "app.py", "def hello():\n    return 'ok'\n")

    ctx = RunContext(
        repo_path=tmp_path,
        mode="full",
        base=None,
        output_dir=tmp_path / ".riskmap",
        provider="auto",
        no_llm=True,
        support_level="l2",
    )

    result, code, _ = run_pipeline(ctx)
    assert result is None
    assert code == 2


def test_preflight_ignores_fastapi_string_literals_in_tests(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "tests" / "test_literals.py",
        "def test_text_fixture():\n    sample = 'from fastapi import APIRouter\\n@router.post(\"/x\")'\n    assert sample\n",
    )

    ctx = RunContext(
        repo_path=tmp_path,
        mode="full",
        base=None,
        output_dir=tmp_path / ".riskmap",
        provider="auto",
        no_llm=True,
        support_level="l2",
    )

    result, code, _ = run_pipeline(ctx)
    assert result is None
    assert code == 2


def test_pipeline_writes_artifacts(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_other.py", "def test_smoke():\n    assert True\n")

    out_dir = tmp_path / ".riskmap"
    ctx = RunContext(
        repo_path=tmp_path,
        mode="pr",
        base="main",
        output_dir=out_dir,
        provider="auto",
        no_llm=True,
    )

    result, code, _ = run_pipeline(ctx)
    assert code == 0
    assert result is not None
    assert (out_dir / "graph.json").exists()
    assert (out_dir / "findings.raw.json").exists()
    assert (out_dir / "findings.json").exists()
    assert (out_dir / "test_plan.json").exists()
    assert (out_dir / "run_metrics.json").exists()
    assert (out_dir / "report.md").exists()
    assert (out_dir / "pr_summary.md").exists()
    graph = json.loads((out_dir / "graph.json").read_text(encoding="utf-8"))
    assert all(not node["source_ref"].startswith("/") for node in graph["nodes"])
    report = (out_dir / "report.md").read_text(encoding="utf-8")
    assert "Graph Statistics:" in report
    assert "effective_ci_mode:" in report
    pr_summary = (out_dir / "pr_summary.md").read_text(encoding="utf-8")
    assert "confidence=`" in pr_summary
    assert "evidence_refs=`" in pr_summary
    assert "effective_ci_mode:" in pr_summary


def test_full_mode_sets_full_analysis_scope(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )

    out_dir = tmp_path / ".riskmap"
    ctx = RunContext(
        repo_path=tmp_path,
        mode="full",
        base=None,
        output_dir=out_dir,
        provider="auto",
        no_llm=True,
    )

    result, code, _ = run_pipeline(ctx)
    assert code == 0
    assert result is not None
    assert result.analysis_scope == "full"


def test_pr_mode_without_baseline_uses_full_fallback(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_api.py", "import pytest\n\ndef test_create_order():\n    assert True\n")

    out_dir = tmp_path / ".riskmap"
    ctx = RunContext(
        repo_path=tmp_path,
        mode="pr",
        base="main",
        output_dir=out_dir,
        provider="auto",
        no_llm=True,
        baseline_graph=tmp_path / ".riskmap" / "baseline" / "graph.json",
    )

    result, code, notes = run_pipeline(ctx)
    assert code == 0
    assert result is not None
    assert result.analysis_scope == "full_fallback"
    assert any("Baseline graph not found" in note for note in notes)


def test_pr_mode_with_baseline_uses_impacted_scope(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_api.py", "import pytest\n\ndef test_create_order():\n    assert True\n")
    baseline = tmp_path / ".riskmap" / "baseline" / "graph.json"
    write_file(baseline, '{"nodes": []}')

    out_dir = tmp_path / ".riskmap"
    ctx = RunContext(
        repo_path=tmp_path,
        mode="pr",
        base="main",
        output_dir=out_dir,
        provider="auto",
        no_llm=True,
        baseline_graph=baseline,
    )

    with patch("ai_risk_manager.pipeline.run._resolve_changed_files", return_value={"app/api.py"}):
        result, code, notes = run_pipeline(ctx)
    assert code == 0
    assert result is not None
    assert result.analysis_scope == "impacted"
    assert any("Impacted subgraph selected" in note for note in notes)


def test_pr_mode_with_invalid_baseline_uses_full_fallback(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_api.py", "import pytest\n\ndef test_create_order():\n    assert True\n")
    baseline = tmp_path / ".riskmap" / "baseline" / "graph.json"
    write_file(baseline, "not-json")

    out_dir = tmp_path / ".riskmap"
    ctx = RunContext(
        repo_path=tmp_path,
        mode="pr",
        base="main",
        output_dir=out_dir,
        provider="auto",
        no_llm=True,
        baseline_graph=baseline,
    )

    result, code, notes = run_pipeline(ctx)
    assert code == 0
    assert result is not None
    assert result.analysis_scope == "full_fallback"
    assert any("Baseline graph not found or invalid" in note for note in notes)


def test_cli_entrypoint_parsing_and_exit_code(tmp_path: Path) -> None:
    fake_output_dir = tmp_path / ".riskmap"
    expected_ctx = RunContext(
        repo_path=tmp_path.resolve(),
        mode="pr",
        base="main",
        output_dir=fake_output_dir.resolve(),
        provider="auto",
        no_llm=True,
        baseline_graph=None,
    )

    with patch("ai_risk_manager.cli.run_pipeline", return_value=(None, 2, ["unsupported"])) as mock_run:
        code = main(
            [
                "analyze",
                str(tmp_path),
                "--mode",
                "pr",
                "--base",
                "main",
                "--no-llm",
                "--output-dir",
                str(fake_output_dir),
            ]
        )
        assert code == 2
        ctx = mock_run.call_args[0][0]
        assert ctx == expected_ctx


def test_collector_supports_chained_router_access(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\n"
        "class App:\n"
        "    router = APIRouter()\n"
        "app = App()\n\n"
        "@app.router.post('/orders')\n"
        "def create_order():\n"
        "    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_orders.py", "import pytest\n\ndef test_create_order():\n    assert True\n")

    ctx = RunContext(
        repo_path=tmp_path,
        mode="full",
        base=None,
        output_dir=tmp_path / ".riskmap",
        provider="auto",
        no_llm=True,
    )
    result, code, _ = run_pipeline(ctx)
    assert code == 0
    assert result is not None
    assert any(node.name == "create_order" for node in result.graph.nodes if node.type == "API")


def test_explicit_provider_unavailable_returns_exit_1(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_orders.py", "import pytest\n\ndef test_create_order():\n    assert True\n")

    with patch("ai_risk_manager.agents.provider._has_api_credentials", return_value=False):
        with patch("ai_risk_manager.agents.provider._has_cli_backend", return_value=False):
            code = main(
                [
                    "analyze",
                    str(tmp_path),
                    "--provider",
                    "api",
                ]
            )
    assert code == 1


def test_pipeline_writes_metadata_to_json_artifacts(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_orders.py", "import pytest\n\ndef test_create_order():\n    assert True\n")

    out_dir = tmp_path / ".riskmap"
    ctx = RunContext(
        repo_path=tmp_path,
        mode="full",
        base=None,
        output_dir=out_dir,
        provider="auto",
        no_llm=True,
    )
    _, code, _ = run_pipeline(ctx)
    assert code == 0

    payload = json.loads((out_dir / "findings.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.1"
    assert "generated_at" in payload
    assert payload["tool_version"] == "0.1.0"

    metrics = json.loads((out_dir / "run_metrics.json").read_text(encoding="utf-8"))
    assert "verification_pass_rate" in metrics
    assert "evidence_completeness" in metrics
    assert "triage_time_proxy_min" in metrics


def test_pipeline_applies_airiskignore_suppressions(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_orders.py", "import pytest\n\ndef test_smoke():\n    assert True\n")
    write_file(
        tmp_path / ".airiskignore",
        "- rule: \"critical_path_no_tests\"\n  file: \"app/api.py\"\n",
    )

    out_dir = tmp_path / ".riskmap"
    ctx = RunContext(
        repo_path=tmp_path,
        mode="full",
        base=None,
        output_dir=out_dir,
        provider="auto",
        no_llm=True,
    )
    result, code, _ = run_pipeline(ctx)
    assert code == 0
    assert result is not None
    assert result.suppressed_count == 1
    assert not result.findings.findings


def test_format_md_only_skips_json_artifacts(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_orders.py", "import pytest\n\ndef test_smoke():\n    assert True\n")

    out_dir = tmp_path / ".riskmap"
    code = main(["analyze", str(tmp_path), "--format", "md", "--no-llm", "--output-dir", str(out_dir)])
    assert code == 0
    assert (out_dir / "report.md").exists()
    assert not (out_dir / "findings.json").exists()


def test_fail_on_severity_returns_exit_3(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_orders.py", "import pytest\n\ndef test_smoke():\n    assert True\n")

    code = main(["analyze", str(tmp_path), "--no-llm", "--fail-on-severity", "high"])
    assert code == 3


def test_cli_parses_new_flags(tmp_path: Path, write_file) -> None:
    fake_output_dir = tmp_path / ".riskmap"
    suppress_file = tmp_path / ".airiskignore"
    write_file(suppress_file, "- key: \"k\"\n")
    expected_ctx = RunContext(
        repo_path=tmp_path.resolve(),
        mode="full",
        base=None,
        output_dir=fake_output_dir.resolve(),
        provider="auto",
        no_llm=True,
        output_format="json",
        fail_on_severity="medium",
        suppress_file=suppress_file.resolve(),
        baseline_graph=None,
        analysis_engine="hybrid",
        only_new=True,
        min_confidence="high",
        ci_mode="soft",
        support_level="l1",
        risk_policy="aggressive",
    )

    with patch("ai_risk_manager.cli.run_pipeline", return_value=(None, 2, ["unsupported"])) as mock_run:
        code = main(
            [
                "analyze",
                str(tmp_path),
                "--no-llm",
                "--format",
                "json",
                "--analysis-engine",
                "hybrid",
                "--only-new",
                "--min-confidence",
                "high",
                "--ci-mode",
                "soft",
                "--support-level",
                "l1",
                "--risk-policy",
                "aggressive",
                "--fail-on-severity",
                "medium",
                "--suppress-file",
                str(suppress_file),
                "--output-dir",
                str(fake_output_dir),
            ]
        )
        assert code == 2
        ctx = mock_run.call_args[0][0]
        assert ctx == expected_ctx


def test_ci_mode_matrix_resolution_by_support_level() -> None:
    cases = [
        ("advisory", "l0", "advisory", None),
        ("soft", "l0", "advisory", "support_level=l0"),
        ("block_new_critical", "l0", "advisory", "support_level=l0"),
        ("advisory", "l1", "advisory", None),
        ("soft", "l1", "soft", None),
        ("block_new_critical", "l1", "soft", "support_level=l1"),
        ("advisory", "l2", "advisory", None),
        ("soft", "l2", "soft", None),
        ("block_new_critical", "l2", "block_new_critical", None),
    ]

    for requested, support_level, expected, note_marker in cases:
        resolved, note = _resolve_effective_ci_mode(requested, support_level)
        assert resolved == expected
        if note_marker is None:
            assert note is None
        else:
            assert note is not None
            assert note_marker in note


def test_ci_mode_block_new_critical_blocks_only_new_critical(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    baseline = tmp_path / ".riskmap" / "baseline" / "graph.json"
    write_file(baseline, '{"nodes": []}')

    critical = FindingsReport(
        findings=[
            Finding(
                id="critical:new",
                rule_id="critical_new_risk",
                title="Critical new risk",
                description="d",
                severity="critical",
                confidence="high",
                evidence="e",
                source_ref="app/api.py:1",
                suppression_key="critical:new",
                recommendation="fix now",
                evidence_refs=["app/api.py:1"],
            )
        ],
        generated_without_llm=True,
    )

    ctx = RunContext(
        repo_path=tmp_path,
        mode="pr",
        base="main",
        output_dir=tmp_path / ".riskmap",
        provider="auto",
        no_llm=True,
        baseline_graph=baseline,
        ci_mode="block_new_critical",
        support_level="l2",
    )

    with patch("ai_risk_manager.pipeline.run.run_rules", return_value=critical):
        with patch("ai_risk_manager.pipeline.run._resolve_changed_files", return_value={"app/api.py"}):
            result, code, notes = run_pipeline(ctx)
    assert code == 3
    assert result is not None
    assert result.summary.effective_ci_mode == "block_new_critical"
    assert any("block_new_critical" in note for note in notes)


def test_ci_mode_block_new_critical_ignores_unverified_findings(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    baseline = tmp_path / ".riskmap" / "baseline" / "graph.json"
    write_file(baseline, '{"nodes": []}')

    critical = FindingsReport(
        findings=[
            Finding(
                id="critical:new",
                rule_id="critical_new_risk",
                title="Critical new risk",
                description="d",
                severity="critical",
                confidence="high",
                evidence="e",
                source_ref="app/api.py:1",
                suppression_key="critical:new",
                recommendation="fix now",
                evidence_refs=["missing/file.py:1"],
            )
        ],
        generated_without_llm=True,
    )

    ctx = RunContext(
        repo_path=tmp_path,
        mode="pr",
        base="main",
        output_dir=tmp_path / ".riskmap",
        provider="auto",
        no_llm=True,
        baseline_graph=baseline,
        ci_mode="block_new_critical",
        support_level="l2",
    )

    with patch("ai_risk_manager.pipeline.run.run_rules", return_value=critical):
        with patch("ai_risk_manager.pipeline.run._resolve_changed_files", return_value={"app/api.py"}):
            result, code, notes = run_pipeline(ctx)
    assert code == 0
    assert result is not None
    assert result.summary.effective_ci_mode == "block_new_critical"
    assert not any("block_new_critical triggered" in note for note in notes)


def test_ci_mode_l1_downgrades_block_to_soft_and_blocks_unverified_critical(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    baseline = tmp_path / ".riskmap" / "baseline" / "graph.json"
    write_file(baseline, '{"nodes": []}')

    critical = FindingsReport(
        findings=[
            Finding(
                id="critical:new",
                rule_id="critical_new_risk",
                title="Critical new risk",
                description="d",
                severity="critical",
                confidence="high",
                evidence="e",
                source_ref="app/api.py:1",
                suppression_key="critical:new",
                recommendation="fix now",
                evidence_refs=["missing/file.py:1"],
            )
        ],
        generated_without_llm=True,
    )

    ctx = RunContext(
        repo_path=tmp_path,
        mode="pr",
        base="main",
        output_dir=tmp_path / ".riskmap",
        provider="auto",
        no_llm=True,
        baseline_graph=baseline,
        ci_mode="block_new_critical",
        support_level="l1",
    )

    with patch("ai_risk_manager.pipeline.run.run_rules", return_value=critical):
        with patch("ai_risk_manager.pipeline.run._resolve_changed_files", return_value={"app/api.py"}):
            result, code, notes = run_pipeline(ctx)
    assert code == 3
    assert result is not None
    assert result.summary.effective_ci_mode == "soft"
    assert any("support_level=l1" in note for note in notes)
    assert any("ci_mode=soft triggered" in note for note in notes)


def test_pr_baseline_status_and_only_new_summary(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    baseline = tmp_path / ".riskmap" / "baseline" / "graph.json"
    write_file(baseline, '{"nodes": []}')
    write_file(
        baseline.parent / "findings.json",
        json.dumps({"findings": [{"fingerprint": "fp-keep"}, {"fingerprint": "fp-resolved"}]}),
    )

    mocked = FindingsReport(
        findings=[
            Finding(
                id="f1",
                rule_id="critical_path_no_tests",
                title="Existing issue",
                description="d",
                severity="high",
                confidence="high",
                evidence="e",
                source_ref="app/api.py:1",
                suppression_key="f1",
                recommendation="r",
                evidence_refs=["app/api.py:1"],
                fingerprint="fp-keep",
            )
        ],
        generated_without_llm=True,
    )

    ctx = RunContext(
        repo_path=tmp_path,
        mode="pr",
        base="main",
        output_dir=tmp_path / ".riskmap",
        provider="auto",
        no_llm=True,
        baseline_graph=baseline,
        only_new=True,
    )

    with patch("ai_risk_manager.pipeline.run.run_rules", return_value=mocked):
        with patch("ai_risk_manager.pipeline.run._resolve_changed_files", return_value={"app/api.py"}):
            result, code, _ = run_pipeline(ctx)

    assert code == 0
    assert result is not None
    assert result.summary.new_count == 0
    assert result.summary.resolved_count == 1
    assert result.summary.unchanged_count == 1
    pr_summary = (ctx.output_dir / "pr_summary.md").read_text(encoding="utf-8")
    assert "No findings in current PR scope." in pr_summary


def test_pipeline_returns_exit_2_when_no_plugin_for_detected_stack(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )

    ctx = RunContext(
        repo_path=tmp_path,
        mode="full",
        base=None,
        output_dir=tmp_path / ".riskmap",
        provider="auto",
        no_llm=True,
        support_level="l2",
    )

    with patch(
        "ai_risk_manager.pipeline.run.detect_stack",
        return_value=StackDetectionResult(stack_id="unknown", confidence="low", reasons=["unknown stack"]),
    ):
        result, code, notes = run_pipeline(ctx)

    assert result is None
    assert code == 2
    assert any("No collector plugin is registered" in note for note in notes)


def test_unknown_stack_auto_uses_l0_advisory_and_does_not_fail(tmp_path: Path, write_file) -> None:
    write_file(tmp_path / "app.py", "print('plain python')\n")
    ctx = RunContext(
        repo_path=tmp_path,
        mode="full",
        base=None,
        output_dir=tmp_path / ".riskmap",
        provider="auto",
        no_llm=True,
        support_level="auto",
        ci_mode="block_new_critical",
    )

    with patch(
        "ai_risk_manager.pipeline.run.detect_stack",
        return_value=StackDetectionResult(stack_id="unknown", confidence="low", reasons=["unknown stack"]),
    ):
        result, code, notes = run_pipeline(ctx)

    assert code == 0
    assert result is not None
    assert result.summary.support_level_applied == "l0"
    assert result.summary.effective_ci_mode == "advisory"
    assert any("ci_mode overridden to advisory" in note for note in notes)


def test_pipeline_reuses_probe_data_for_preflight(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_orders.py", "import pytest\n\ndef test_smoke():\n    assert True\n")

    ctx = RunContext(
        repo_path=tmp_path,
        mode="full",
        base=None,
        output_dir=tmp_path / ".riskmap",
        provider="auto",
        no_llm=True,
    )

    from ai_risk_manager.collectors.plugins import fastapi as fastapi_plugin

    with patch(
        "ai_risk_manager.collectors.plugins.fastapi.scan_fastapi_signals",
        wraps=fastapi_plugin.scan_fastapi_signals,
    ) as scan_mock:
        result, code, _ = run_pipeline(ctx)

    assert result is not None
    assert code == 0
    assert scan_mock.call_count == 1


def test_pipeline_reports_broken_invariant_on_unguarded_transition(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.post('/orders/{order_id}/pay')\n"
        "def pay_order(order_id: str):\n"
        "    status = 'pending'\n"
        "    if status == 'pending':\n"
        "        status = 'paid'\n"
        "    return {'order_id': order_id, 'status': status}\n",
    )
    write_file(tmp_path / "tests" / "test_pay_order.py", "def test_pay_order():\n    assert True\n")

    ctx = RunContext(
        repo_path=tmp_path,
        mode="full",
        base=None,
        output_dir=tmp_path / ".riskmap",
        provider="auto",
        no_llm=True,
    )
    result, code, _ = run_pipeline(ctx)
    assert code == 0
    assert result is not None
    rule_ids = {finding.rule_id for finding in result.findings.findings}
    assert "broken_invariant_on_transition" in rule_ids


def test_pipeline_skips_broken_invariant_when_transition_is_declared(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "ALLOWED_TRANSITIONS = {'pending': ['paid']}\n"
        "@router.post('/orders/{order_id}/pay')\n"
        "def pay_order(order_id: str):\n"
        "    status = 'pending'\n"
        "    if status == 'pending':\n"
        "        status = 'paid'\n"
        "    return {'order_id': order_id, 'status': status}\n",
    )
    write_file(tmp_path / "tests" / "test_pay_order.py", "def test_pay_order():\n    assert True\n")

    ctx = RunContext(
        repo_path=tmp_path,
        mode="full",
        base=None,
        output_dir=tmp_path / ".riskmap",
        provider="auto",
        no_llm=True,
    )
    result, code, _ = run_pipeline(ctx)
    assert code == 0
    assert result is not None
    rule_ids = {finding.rule_id for finding in result.findings.findings}
    assert "broken_invariant_on_transition" not in rule_ids


def test_pipeline_skips_broken_invariant_when_guard_exists(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.post('/orders/{order_id}/pay')\n"
        "def pay_order(order_id: str):\n"
        "    status = 'pending'\n"
        "    can_transition = order_id != ''\n"
        "    if status == 'pending':\n"
        "        assert can_transition\n"
        "        status = 'paid'\n"
        "    return {'order_id': order_id, 'status': status}\n",
    )
    write_file(tmp_path / "tests" / "test_pay_order.py", "def test_pay_order():\n    assert True\n")

    ctx = RunContext(
        repo_path=tmp_path,
        mode="full",
        base=None,
        output_dir=tmp_path / ".riskmap",
        provider="auto",
        no_llm=True,
    )
    result, code, _ = run_pipeline(ctx)
    assert code == 0
    assert result is not None
    rule_ids = {finding.rule_id for finding in result.findings.findings}
    assert "broken_invariant_on_transition" not in rule_ids


def test_pipeline_reports_dependency_policy_violation(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.post('/orders')\n"
        "def create_order():\n"
        "    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_api.py", "def test_create_order():\n    assert True\n")
    write_file(tmp_path / "requirements.txt", "fastapi==0.110.0\nrequests>=2.31.0\n")

    ctx = RunContext(
        repo_path=tmp_path,
        mode="full",
        base=None,
        output_dir=tmp_path / ".riskmap",
        provider="auto",
        no_llm=True,
    )

    result, code, _ = run_pipeline(ctx)
    assert code == 0
    assert result is not None
    rule_ids = {finding.rule_id for finding in result.findings.findings}
    assert "dependency_risk_policy_violation" in rule_ids


def test_pipeline_skips_dependency_policy_when_versions_are_pinned(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.post('/orders')\n"
        "def create_order():\n"
        "    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_api.py", "def test_create_order():\n    assert True\n")
    write_file(tmp_path / "requirements.txt", "fastapi==0.110.0\nrequests==2.31.0\n")

    ctx = RunContext(
        repo_path=tmp_path,
        mode="full",
        base=None,
        output_dir=tmp_path / ".riskmap",
        provider="auto",
        no_llm=True,
    )

    result, code, _ = run_pipeline(ctx)
    assert code == 0
    assert result is not None
    rule_ids = {finding.rule_id for finding in result.findings.findings}
    assert "dependency_risk_policy_violation" not in rule_ids


def _dependency_violation_kinds(result) -> set[str]:
    kinds: set[str] = set()
    for finding in result.findings.findings:
        if finding.rule_id != "dependency_risk_policy_violation":
            continue
        if "(" in finding.title and finding.title.endswith(")"):
            kinds.add(finding.title.rsplit("(", 1)[1][:-1])
    return kinds


def _dependency_violation_severity_by_kind(result) -> dict[str, str]:
    severity_by_kind: dict[str, str] = {}
    for finding in result.findings.findings:
        if finding.rule_id != "dependency_risk_policy_violation":
            continue
        if "(" not in finding.title or not finding.title.endswith(")"):
            continue
        kind = finding.title.rsplit("(", 1)[1][:-1]
        severity_by_kind[kind] = finding.severity
    return severity_by_kind


def test_pipeline_dependency_policy_profiles_control_violation_sensitivity(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.post('/orders')\n"
        "def create_order():\n"
        "    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_api.py", "def test_create_order():\n    assert True\n")
    write_file(
        tmp_path / "requirements.txt",
        "fastapi==0.110.0\nrequests>=2.31.0\npytest\ninternal-lib @ git+https://example.com/internal.git\n",
    )

    base_ctx = dict(
        repo_path=tmp_path,
        mode="full",
        base=None,
        output_dir=tmp_path / ".riskmap",
        provider="auto",
        no_llm=True,
    )

    conservative_result, code, _ = run_pipeline(RunContext(**base_ctx, risk_policy="conservative"))
    assert code == 0
    assert conservative_result is not None
    assert _dependency_violation_kinds(conservative_result) == {"direct_reference"}

    balanced_result, code, _ = run_pipeline(RunContext(**base_ctx, risk_policy="balanced"))
    assert code == 0
    assert balanced_result is not None
    assert _dependency_violation_kinds(balanced_result) == {"direct_reference", "range_not_pinned"}

    aggressive_result, code, _ = run_pipeline(RunContext(**base_ctx, risk_policy="aggressive"))
    assert code == 0
    assert aggressive_result is not None
    assert _dependency_violation_kinds(aggressive_result) == {
        "direct_reference",
        "range_not_pinned",
        "unpinned_version",
    }


def test_pipeline_dependency_severity_is_lower_for_development_scope(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.post('/orders')\n"
        "def create_order():\n"
        "    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_api.py", "def test_create_order():\n    assert True\n")
    write_file(tmp_path / "requirements.txt", "requests>=2.31.0\n")
    write_file(tmp_path / "requirements-dev.txt", "pytest>=8.0\n")

    result, code, _ = run_pipeline(
        RunContext(
            repo_path=tmp_path,
            mode="full",
            base=None,
            output_dir=tmp_path / ".riskmap",
            provider="auto",
            no_llm=True,
            risk_policy="balanced",
        )
    )
    assert code == 0
    assert result is not None

    dep_findings = [f for f in result.findings.findings if f.rule_id == "dependency_risk_policy_violation"]
    runtime_range = [f for f in dep_findings if "requirements.txt" in f.source_ref and "range_not_pinned" in f.title]
    dev_range = [f for f in dep_findings if "requirements-dev.txt" in f.source_ref and "range_not_pinned" in f.title]
    assert runtime_range
    assert dev_range
    assert runtime_range[0].severity == "medium"
    assert dev_range[0].severity == "low"
