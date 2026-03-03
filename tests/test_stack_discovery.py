from __future__ import annotations

from pathlib import Path

from ai_risk_manager.stacks.discovery import detect_stack


def test_detect_stack_fastapi_pytest_high_confidence(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_api.py", "import pytest\n\ndef test_create_order():\n    assert True\n")

    detected = detect_stack(tmp_path)
    assert detected.stack_id == "fastapi_pytest"
    assert detected.confidence == "high"


def test_detect_stack_unknown_for_plain_python_repo(tmp_path: Path, write_file) -> None:
    write_file(tmp_path / "app.py", "def hello():\n    return 'ok'\n")

    detected = detect_stack(tmp_path)
    assert detected.stack_id == "unknown"
    assert detected.confidence == "low"
