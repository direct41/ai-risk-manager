from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from ai_risk_manager.cli import main
from ai_risk_manager.pipeline.run import run_pipeline
from ai_risk_manager.schemas.types import RunContext


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


def test_cli_entrypoint_parsing_and_exit_code(tmp_path: Path) -> None:
    fake_output_dir = tmp_path / ".riskmap"
    expected_ctx = RunContext(
        repo_path=tmp_path.resolve(),
        mode="pr",
        base="main",
        output_dir=fake_output_dir.resolve(),
        provider="auto",
        no_llm=True,
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
