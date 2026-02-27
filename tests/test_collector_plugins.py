from __future__ import annotations

from pathlib import Path

from ai_risk_manager.collectors.plugins.registry import get_plugin_for_stack


def test_registry_returns_fastapi_plugin() -> None:
    plugin = get_plugin_for_stack("fastapi_pytest")
    assert plugin is not None
    assert plugin.stack_id == "fastapi_pytest"


def test_registry_returns_none_for_unknown_stack() -> None:
    assert get_plugin_for_stack("unknown") is None


def test_fastapi_plugin_collects_write_endpoint_and_warns_without_pytest(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )

    plugin = get_plugin_for_stack("fastapi_pytest")
    assert plugin is not None

    preflight = plugin.preflight(tmp_path)
    assert preflight.status == "WARN"

    bundle = plugin.collect(tmp_path)
    endpoint = next((row for row in bundle.write_endpoints if row[1] == "create_order"), None)
    assert endpoint is not None
    assert endpoint[0] == "app/api.py"
    assert endpoint[2] == "POST"
    assert endpoint[3] == "/orders"
    assert endpoint[4] > 0


def test_fastapi_plugin_collects_test_http_calls(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(
        tmp_path / "tests" / "test_api.py",
        "from fastapi.testclient import TestClient\n"
        "def test_create_order(client: TestClient):\n"
        "    response = client.post('/orders', json={'x': 1})\n"
        "    assert response.status_code == 200\n",
    )

    plugin = get_plugin_for_stack("fastapi_pytest")
    assert plugin is not None
    bundle = plugin.collect(tmp_path)
    assert any(call[2] == "POST" and call[3] == "/orders" for call in bundle.test_http_calls)


def test_fastapi_plugin_marks_transition_without_guard(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "main.py",
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

    plugin = get_plugin_for_stack("fastapi_pytest")
    assert plugin is not None
    bundle = plugin.collect(tmp_path)

    transition = next((row for row in bundle.handled_transitions if row[1] == "pay_order"), None)
    assert transition is not None
    assert transition[2] == "pending"
    assert transition[3] == "paid"
    assert transition[6] is False


def test_fastapi_plugin_marks_transition_with_guard(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "main.py",
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

    plugin = get_plugin_for_stack("fastapi_pytest")
    assert plugin is not None
    bundle = plugin.collect(tmp_path)

    transition = next((row for row in bundle.handled_transitions if row[1] == "pay_order"), None)
    assert transition is not None
    assert transition[6] is True
