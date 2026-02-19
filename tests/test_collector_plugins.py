from __future__ import annotations

from pathlib import Path

from ai_risk_manager.collectors.plugins.registry import get_plugin_for_stack


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_registry_returns_fastapi_plugin() -> None:
    plugin = get_plugin_for_stack("fastapi_pytest")
    assert plugin is not None
    assert plugin.stack_id == "fastapi_pytest"


def test_registry_returns_none_for_unknown_stack() -> None:
    assert get_plugin_for_stack("unknown") is None


def test_fastapi_plugin_collects_write_endpoint_and_warns_without_pytest(tmp_path: Path) -> None:
    _write(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )

    plugin = get_plugin_for_stack("fastapi_pytest")
    assert plugin is not None

    preflight = plugin.preflight(tmp_path)
    assert preflight.status == "WARN"

    bundle = plugin.collect(tmp_path)
    assert ("app/api.py", "create_order") in bundle.write_endpoints
