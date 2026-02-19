from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from ai_risk_manager.cli import main
from ai_risk_manager.pipeline.run import run_pipeline
from ai_risk_manager.schemas.types import RunContext
from ai_risk_manager.stacks.discovery import StackDetectionResult


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_preflight_fail_for_non_fastapi(tmp_path: Path) -> None:
    _write(tmp_path / "app.py", "def hello():\n    return 'ok'\n")

    ctx = RunContext(
        repo_path=tmp_path,
        mode="full",
        base=None,
        output_dir=tmp_path / ".riskmap",
        provider="auto",
        no_llm=True,
    )

    result, code, _ = run_pipeline(ctx)
    assert result is None
    assert code == 2


def test_preflight_ignores_fastapi_string_literals_in_tests(tmp_path: Path) -> None:
    _write(
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
    )

    result, code, _ = run_pipeline(ctx)
    assert result is None
    assert code == 2


def test_pipeline_writes_artifacts(tmp_path: Path) -> None:
    _write(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    _write(tmp_path / "tests" / "test_other.py", "def test_smoke():\n    assert True\n")

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
    assert (out_dir / "report.md").exists()
    assert (out_dir / "pr_summary.md").exists()
    graph = json.loads((out_dir / "graph.json").read_text(encoding="utf-8"))
    assert all(not node["source_ref"].startswith("/") for node in graph["nodes"])
    report = (out_dir / "report.md").read_text(encoding="utf-8")
    assert "Graph Statistics:" in report


def test_full_mode_sets_full_analysis_scope(tmp_path: Path) -> None:
    _write(
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


def test_pr_mode_without_baseline_uses_full_fallback(tmp_path: Path) -> None:
    _write(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    _write(tmp_path / "tests" / "test_api.py", "import pytest\n\ndef test_create_order():\n    assert True\n")

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


def test_pr_mode_with_baseline_uses_impacted_scope(tmp_path: Path) -> None:
    _write(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    _write(tmp_path / "tests" / "test_api.py", "import pytest\n\ndef test_create_order():\n    assert True\n")
    baseline = tmp_path / ".riskmap" / "baseline" / "graph.json"
    _write(baseline, '{"nodes": []}')

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


def test_pr_mode_with_invalid_baseline_uses_full_fallback(tmp_path: Path) -> None:
    _write(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    _write(tmp_path / "tests" / "test_api.py", "import pytest\n\ndef test_create_order():\n    assert True\n")
    baseline = tmp_path / ".riskmap" / "baseline" / "graph.json"
    _write(baseline, "not-json")

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


def test_collector_supports_chained_router_access(tmp_path: Path) -> None:
    _write(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\n"
        "class App:\n"
        "    router = APIRouter()\n"
        "app = App()\n\n"
        "@app.router.post('/orders')\n"
        "def create_order():\n"
        "    return {'ok': True}\n",
    )
    _write(tmp_path / "tests" / "test_orders.py", "import pytest\n\ndef test_create_order():\n    assert True\n")

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


def test_explicit_provider_unavailable_returns_exit_1(tmp_path: Path) -> None:
    _write(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    _write(tmp_path / "tests" / "test_orders.py", "import pytest\n\ndef test_create_order():\n    assert True\n")

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


def test_pipeline_writes_metadata_to_json_artifacts(tmp_path: Path) -> None:
    _write(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    _write(tmp_path / "tests" / "test_orders.py", "import pytest\n\ndef test_create_order():\n    assert True\n")

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
    assert payload["schema_version"] == "1.0"
    assert "generated_at" in payload
    assert payload["tool_version"] == "0.1.0"


def test_pipeline_applies_airiskignore_suppressions(tmp_path: Path) -> None:
    _write(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    _write(tmp_path / "tests" / "test_orders.py", "import pytest\n\ndef test_smoke():\n    assert True\n")
    _write(
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


def test_format_md_only_skips_json_artifacts(tmp_path: Path) -> None:
    _write(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    _write(tmp_path / "tests" / "test_orders.py", "import pytest\n\ndef test_smoke():\n    assert True\n")

    out_dir = tmp_path / ".riskmap"
    code = main(["analyze", str(tmp_path), "--format", "md", "--no-llm", "--output-dir", str(out_dir)])
    assert code == 0
    assert (out_dir / "report.md").exists()
    assert not (out_dir / "findings.json").exists()


def test_fail_on_severity_returns_exit_3(tmp_path: Path) -> None:
    _write(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    _write(tmp_path / "tests" / "test_orders.py", "import pytest\n\ndef test_smoke():\n    assert True\n")

    code = main(["analyze", str(tmp_path), "--no-llm", "--fail-on-severity", "high"])
    assert code == 3


def test_cli_parses_new_flags(tmp_path: Path) -> None:
    fake_output_dir = tmp_path / ".riskmap"
    suppress_file = tmp_path / ".airiskignore"
    _write(suppress_file, "- key: \"k\"\n")
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
    )

    with patch("ai_risk_manager.cli.run_pipeline", return_value=(None, 2, ["unsupported"])) as mock_run:
        code = main(
            [
                "analyze",
                str(tmp_path),
                "--no-llm",
                "--format",
                "json",
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


def test_pipeline_returns_exit_2_when_no_plugin_for_detected_stack(tmp_path: Path) -> None:
    _write(
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
    )

    with patch(
        "ai_risk_manager.pipeline.run.detect_stack",
        return_value=StackDetectionResult(stack_id="unknown", confidence="low", reasons=["unknown stack"]),
    ):
        result, code, notes = run_pipeline(ctx)

    assert result is None
    assert code == 2
    assert any("No collector plugin is registered" in note for note in notes)


def test_pipeline_reuses_probe_data_for_preflight(tmp_path: Path) -> None:
    _write(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    _write(tmp_path / "tests" / "test_orders.py", "import pytest\n\ndef test_smoke():\n    assert True\n")

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
