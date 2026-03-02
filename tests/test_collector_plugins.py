from __future__ import annotations

from pathlib import Path

from ai_risk_manager.collectors.plugins.registry import get_plugin_for_stack


def test_registry_returns_fastapi_plugin() -> None:
    plugin = get_plugin_for_stack("fastapi_pytest")
    assert plugin is not None
    assert plugin.stack_id == "fastapi_pytest"


def test_registry_returns_django_plugin() -> None:
    plugin = get_plugin_for_stack("django_drf")
    assert plugin is not None
    assert plugin.stack_id == "django_drf"


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


def test_fastapi_plugin_collects_dependency_specs_from_requirements(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(
        tmp_path / "requirements.txt",
        "fastapi==0.110.0\nrequests>=2.31.0\ninternal-lib @ git+https://example.com/internal.git\n",
    )

    plugin = get_plugin_for_stack("fastapi_pytest")
    assert plugin is not None
    bundle = plugin.collect(tmp_path)

    violations = {(name, violation, scope) for _, name, _, _, violation, scope in bundle.dependency_specs}
    assert ("fastapi", None, "runtime") in violations
    assert ("requests", "range_not_pinned", "runtime") in violations
    assert ("internal-lib", "direct_reference", "runtime") in violations


def test_fastapi_plugin_collects_project_dependencies_from_pyproject(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(
        tmp_path / "pyproject.toml",
        "[project]\nname='demo'\nversion='0.1.0'\ndependencies=['httpx>=0.27','uvicorn==0.30.0']\n",
    )

    plugin = get_plugin_for_stack("fastapi_pytest")
    assert plugin is not None
    bundle = plugin.collect(tmp_path)

    violations = {(name, violation, scope) for _, name, _, _, violation, scope in bundle.dependency_specs}
    assert ("httpx", "range_not_pinned", "runtime") in violations
    assert ("uvicorn", None, "runtime") in violations


def test_fastapi_plugin_marks_dev_dependency_scope_from_optional_group(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(
        tmp_path / "pyproject.toml",
        "[project]\n"
        "name='demo'\n"
        "version='0.1.0'\n"
        "dependencies=['fastapi==0.110.0']\n"
        "optional-dependencies={dev=['pytest>=8.0']}\n",
    )

    plugin = get_plugin_for_stack("fastapi_pytest")
    assert plugin is not None
    bundle = plugin.collect(tmp_path)

    violations = {(name, violation, scope) for _, name, _, _, violation, scope in bundle.dependency_specs}
    assert ("pytest", "range_not_pinned", "development") in violations


def test_fastapi_plugin_marks_dev_scope_from_requirements_filename(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "requirements-dev.txt", "pytest>=8.0\n")

    plugin = get_plugin_for_stack("fastapi_pytest")
    assert plugin is not None
    bundle = plugin.collect(tmp_path)

    violations = {(name, violation, scope) for _, name, _, _, violation, scope in bundle.dependency_specs}
    assert ("pytest", "range_not_pinned", "development") in violations


def test_fastapi_plugin_skips_eval_and_fixture_directories(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(
        tmp_path / "eval" / "repos" / "fixture_app.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\nALLOWED_TRANSITIONS={'pending':['paid']}\n",
    )
    write_file(
        tmp_path / "fixtures" / "fixture_api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/fixture')\ndef fixture_ep():\n    return {'ok': True}\n",
    )
    write_file(
        tmp_path / "testdata" / "fixture_test.py",
        "def test_fixture():\n    assert True\n",
    )

    plugin = get_plugin_for_stack("fastapi_pytest")
    assert plugin is not None
    bundle = plugin.collect(tmp_path)

    collected_refs = {
        *[row[0] for row in bundle.write_endpoints],
        *[row[0] for row in bundle.declared_transitions],
        *[row[0] for row in bundle.test_cases],
    }
    assert "app/api.py" in collected_refs
    assert all(not ref.startswith("eval/") for ref in collected_refs)
    assert all(not ref.startswith("fixtures/") for ref in collected_refs)
    assert all(not ref.startswith("testdata/") for ref in collected_refs)


def test_django_plugin_collects_write_endpoint_and_test_http_call(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "views.py",
        "from rest_framework.views import APIView\n"
        "from rest_framework.response import Response\n"
        "class PayOrderView(APIView):\n"
        "    def post(self, request, order_id: str):\n"
        "        return Response({'order_id': order_id, 'status': 'paid'})\n",
    )
    write_file(
        tmp_path / "app" / "urls.py",
        "from django.urls import path\n"
        "from .views import PayOrderView\n"
        "urlpatterns = [\n"
        "    path('orders/<str:order_id>/pay/', PayOrderView.as_view(), name='pay-order'),\n"
        "]\n",
    )
    write_file(
        tmp_path / "tests" / "test_pay.py",
        "def test_pay_order(client):\n"
        "    response = client.post('/orders/ord_1/pay/')\n"
        "    assert response.status_code in {200, 201, 202}\n",
    )

    plugin = get_plugin_for_stack("django_drf")
    assert plugin is not None
    preflight = plugin.preflight(tmp_path)
    assert preflight.status in {"PASS", "WARN"}

    bundle = plugin.collect(tmp_path)
    endpoint = next((row for row in bundle.write_endpoints if row[1] == "PayOrderView.post"), None)
    assert endpoint is not None
    assert endpoint[2] == "POST"
    assert endpoint[3] == "/orders/{order_id}/pay"
    assert any(call[2] == "POST" and call[3] == "/orders/ord_1/pay" for call in bundle.test_http_calls)
