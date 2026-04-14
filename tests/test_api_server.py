from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ai_risk_manager.api.server import app
from ai_risk_manager.pipeline.run import run_pipeline
from ai_risk_manager.schemas.types import RunContext
from ai_risk_manager.stacks.discovery import StackDetectionResult

pytest.importorskip("httpx")
TestClient = pytest.importorskip("fastapi.testclient").TestClient


def test_healthz_returns_ok_and_version() -> None:
    client = TestClient(app)
    response = client.get("/healthz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "version" in payload


def test_api_analyze_matches_pipeline_for_same_input(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_other.py", "def test_smoke():\n    assert True\n")

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
    assert api_data["summary"] is not None
    assert "new_count" in api_data["summary"]
    assert "effective_ci_mode" in api_data["summary"]
    assert api_data["result"]["analysis_scope"] == direct_result.analysis_scope
    assert len(api_data["result"]["findings"]["findings"]) == len(direct_result.findings.findings)
    assert isinstance(api_data["correlation_id"], str)
    assert api_data["diagnostics"]["status"] == "completed"
    assert isinstance(api_data["diagnostics"]["duration_ms"], int)
    assert api_data["artifacts"]["api_audit.json"].endswith("api_audit.json")
    assert (output_dir / "api_audit.json").exists()


def test_api_pr_mode_exposes_pr_summary_artifacts(tmp_path: Path, write_file) -> None:
    write_file(tmp_path / "src" / "service.py", "def mutate(payload):\n    return payload\n")

    output_dir = tmp_path / ".riskmap_pr_api"
    payload = {
        "path": str(tmp_path),
        "mode": "pr",
        "base": "main",
        "no_llm": True,
        "output_dir": str(output_dir),
        "format": "json",
        "support_level": "auto",
    }

    client = TestClient(app)
    with patch(
        "ai_risk_manager.pipeline.run.detect_stack",
        return_value=StackDetectionResult(stack_id="unknown", confidence="low", reasons=["unknown stack"]),
    ):
        with patch("ai_risk_manager.pipeline.run._resolve_changed_files", return_value={"src/service.py"}):
            response = client.post("/v1/analyze", json=payload)

    assert response.status_code == 200
    api_data = response.json()
    assert api_data["artifacts"]["github_check.json"].endswith("github_check.json")
    assert api_data["artifacts"]["pr_summary.json"].endswith("pr_summary.json")
    pr_summary = json.loads((output_dir / "pr_summary.json").read_text(encoding="utf-8"))
    assert pr_summary["marker"] == "ai-risk-manager"
    assert "top_findings" in pr_summary


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


def test_api_returns_exit_1_for_unavailable_explicit_provider(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_api.py", "import pytest\n\ndef test_create_order():\n    assert True\n")

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


def test_api_respects_fail_on_severity_and_returns_exit_3(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_api.py", "import pytest\n\ndef test_smoke():\n    assert True\n")

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


def test_api_accepts_ai_first_request_fields(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_api.py", "import pytest\n\ndef test_create_order():\n    assert True\n")

    client = TestClient(app)
    response = client.post(
        "/v1/analyze",
        json={
            "path": str(tmp_path),
            "mode": "full",
            "no_llm": True,
            "analysis_engine": "ai_first",
            "only_new": True,
            "min_confidence": "low",
            "ci_mode": "advisory",
            "support_level": "auto",
            "risk_policy": "balanced",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["exit_code"] == 0
    assert payload["summary"]["support_level_applied"] in {"l0", "l1", "l2"}
    assert payload["summary"]["effective_ci_mode"] == "advisory"
    assert "verification_pass_rate" in payload["summary"]
    assert "evidence_completeness" in payload["summary"]
    assert payload["summary"]["competitive_mode"] in {"deterministic", "hybrid"}
    assert payload["summary"]["graph_mode_applied"] in {"deterministic", "enriched"}
    assert isinstance(payload["summary"]["semantic_signal_count"], int)


def test_api_requires_token_when_airisk_api_token_is_configured(tmp_path: Path, write_file, monkeypatch) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_api.py", "def test_smoke():\n    assert True\n")
    monkeypatch.setenv("AIRISK_API_TOKEN", "secret-token")

    client = TestClient(app)
    payload = {
        "path": str(tmp_path),
        "mode": "full",
        "no_llm": True,
        "output_dir": str(tmp_path / "untrusted-audit-dir"),
    }
    unauthorized = client.post("/v1/analyze", json=payload)
    assert unauthorized.status_code == 401
    assert unauthorized.json()["detail"] == "Unauthorized"
    assert not (tmp_path / "untrusted-audit-dir" / "api_audit.json").exists()

    wrong_key = client.post("/v1/analyze", json=payload, headers={"X-API-Key": "wrong"})
    assert wrong_key.status_code == 401

    with_api_key = client.post("/v1/analyze", json=payload, headers={"X-API-Key": "secret-token"})
    assert with_api_key.status_code == 200

    with_bearer = client.post("/v1/analyze", json=payload, headers={"Authorization": "Bearer secret-token"})
    assert with_bearer.status_code == 200


def test_api_respects_rate_limit_when_configured(tmp_path: Path, write_file, monkeypatch) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_api.py", "def test_smoke():\n    assert True\n")
    monkeypatch.setenv("AIRISK_API_RATE_LIMIT_PER_MINUTE", "1")

    client = TestClient(app)
    payload = {
        "path": str(tmp_path),
        "mode": "full",
        "no_llm": True,
    }
    headers = {"X-Forwarded-For": "198.51.100.10"}
    first = client.post("/v1/analyze", json=payload, headers=headers)
    second = client.post("/v1/analyze", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"] == "Rate limit exceeded"


def test_api_rejects_payload_above_max_body_size(tmp_path: Path, write_file, monkeypatch) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_api.py", "def test_smoke():\n    assert True\n")
    monkeypatch.setenv("AIRISK_API_MAX_BODY_BYTES", "120")

    client = TestClient(app)
    response = client.post(
        "/v1/analyze",
        json={
            "path": str(tmp_path),
            "mode": "full",
            "no_llm": True,
            "base": "x" * 300,
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Payload too large"


def test_api_uses_provided_correlation_id(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_api.py", "def test_smoke():\n    assert True\n")

    client = TestClient(app)
    response = client.post(
        "/v1/analyze",
        json={
            "path": str(tmp_path),
            "mode": "full",
            "no_llm": True,
        },
        headers={"X-Correlation-ID": "custom.req-001"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["correlation_id"] == "custom.req-001"
    assert payload["notes"][0] == "correlation_id=custom.req-001"


def test_api_writes_audit_log_when_configured(tmp_path: Path, write_file, monkeypatch) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_api.py", "def test_smoke():\n    assert True\n")
    audit_log = tmp_path / "audit" / "api.jsonl"
    monkeypatch.setenv("AIRISK_API_AUDIT_LOG", str(audit_log))

    client = TestClient(app)
    response = client.post(
        "/v1/analyze",
        json={
            "path": str(tmp_path),
            "mode": "full",
            "no_llm": True,
        },
    )

    assert response.status_code == 200
    lines = [line for line in audit_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["status"] == "completed"
    assert payload["http_status"] == 200
    assert payload["exit_code"] == 0
    assert payload["correlation_id"] == response.json()["correlation_id"]


def test_api_returns_failure_diagnostics_on_internal_error(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_api.py", "def test_smoke():\n    assert True\n")

    client = TestClient(app)
    with patch("ai_risk_manager.api.server.run_pipeline", side_effect=RuntimeError("boom")):
        response = client.post(
            "/v1/analyze",
            json={
                "path": str(tmp_path),
                "mode": "full",
                "no_llm": True,
            },
        )

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["message"] == "Internal server error"
    assert isinstance(detail["correlation_id"], str)
    assert detail["diagnostic_id"].startswith("diag-")
