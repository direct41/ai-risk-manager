from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from ai_risk_manager.api.server import app
from ai_risk_manager.pipeline.run import run_pipeline
from ai_risk_manager.schemas.types import RunContext


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_healthz_returns_ok_and_version() -> None:
    client = TestClient(app)
    response = client.get("/healthz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "version" in payload


def test_api_analyze_matches_pipeline_for_same_input(tmp_path: Path) -> None:
    _write(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    _write(tmp_path / "tests" / "test_other.py", "def test_smoke():\n    assert True\n")

    output_dir = tmp_path / ".riskmap_api"
    payload = {
        "path": str(tmp_path),
        "mode": "full",
        "no_llm": True,
        "output_dir": str(output_dir),
        "format": "json",
    }

    client = TestClient(app)
    response = client.post("/v1/analyze", json=payload)
    assert response.status_code == 200

    api_data = response.json()

    ctx = RunContext(
        repo_path=tmp_path.resolve(),
        mode="full",
        base=None,
        output_dir=output_dir.resolve(),
        provider="auto",
        no_llm=True,
        output_format="json",
    )
    direct_result, direct_code, _ = run_pipeline(ctx)

    assert direct_result is not None
    assert api_data["exit_code"] == direct_code
    assert api_data["result"] is not None
    assert api_data["result"]["analysis_scope"] == direct_result.analysis_scope
    assert len(api_data["result"]["findings"]["findings"]) == len(direct_result.findings.findings)


def test_api_returns_400_for_missing_repo_path(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    client = TestClient(app)
    response = client.post(
        "/v1/analyze",
        json={
            "path": str(missing),
            "mode": "full",
            "no_llm": True,
        },
    )

    assert response.status_code == 400


def test_api_returns_exit_1_for_unavailable_explicit_provider(tmp_path: Path) -> None:
    _write(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    _write(tmp_path / "tests" / "test_api.py", "import pytest\n\ndef test_create_order():\n    assert True\n")

    client = TestClient(app)
    with patch("ai_risk_manager.agents.provider._has_api_credentials", return_value=False):
        with patch("ai_risk_manager.agents.provider._has_cli_backend", return_value=False):
            response = client.post(
                "/v1/analyze",
                json={
                    "path": str(tmp_path),
                    "mode": "full",
                    "provider": "api",
                    "no_llm": False,
                },
            )

    assert response.status_code == 200
    payload = response.json()
    assert payload["exit_code"] == 1
    assert payload["result"] is None


def test_api_respects_fail_on_severity_and_returns_exit_3(tmp_path: Path) -> None:
    _write(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    _write(tmp_path / "tests" / "test_api.py", "import pytest\n\ndef test_smoke():\n    assert True\n")

    client = TestClient(app)
    response = client.post(
        "/v1/analyze",
        json={
            "path": str(tmp_path),
            "mode": "full",
            "no_llm": True,
            "fail_on_severity": "high",
        },
    )

    assert response.status_code == 200
    assert response.json()["exit_code"] == 3
