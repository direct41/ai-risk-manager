from __future__ import annotations

from pathlib import Path

from ai_risk_manager.collectors.plugins.registry import get_plugin_for_stack, get_signal_plugin_for_stack


def test_registry_returns_fastapi_plugin() -> None:
    plugin = get_plugin_for_stack("fastapi_pytest")
    assert plugin is not None
    assert plugin.stack_id == "fastapi_pytest"


def test_registry_returns_django_plugin() -> None:
    plugin = get_plugin_for_stack("django_drf")
    assert plugin is not None
    assert plugin.stack_id == "django_drf"


def test_registry_returns_express_plugin() -> None:
    plugin = get_plugin_for_stack("express_node")
    assert plugin is not None
    assert plugin.stack_id == "express_node"


def test_registry_returns_none_for_unknown_stack() -> None:
    assert get_plugin_for_stack("unknown") is None


def test_registry_returns_signal_plugin_for_fastapi() -> None:
    plugin = get_signal_plugin_for_stack("fastapi_pytest")
    assert plugin is not None
    assert "http_write_surface" in plugin.supported_signal_kinds


def test_fastapi_plugin_collect_signals_from_artifacts(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/orders')\ndef create_order():\n    return {'ok': True}\n",
    )
    write_file(tmp_path / "tests" / "test_api.py", "def test_create_order(client):\n    client.post('/orders')\n")

    plugin = get_signal_plugin_for_stack("fastapi_pytest")
    assert plugin is not None

    bundle = plugin.collect(tmp_path)
    signals = plugin.collect_signals_from_artifacts(bundle)
    kinds = {signal.kind for signal in signals.signals}

    assert "http_write_surface" in kinds
    assert "test_to_endpoint_coverage" in kinds
    assert "dependency_version_policy" in signals.supported_kinds


def test_registry_returns_signal_plugin_for_django() -> None:
    plugin = get_signal_plugin_for_stack("django_drf")
    assert plugin is not None
    assert "http_write_surface" in plugin.supported_signal_kinds
    assert "dependency_version_policy" in plugin.supported_signal_kinds


def test_registry_returns_signal_plugin_for_express() -> None:
    plugin = get_signal_plugin_for_stack("express_node")
    assert plugin is not None
    assert "http_write_surface" in plugin.supported_signal_kinds
    assert "dependency_version_policy" in plugin.supported_signal_kinds
    assert "authorization_boundary_enforced" in plugin.supported_signal_kinds
    assert "write_contract_integrity" in plugin.supported_signal_kinds
    assert "ui_ergonomics" in plugin.supported_signal_kinds


def test_express_plugin_collects_write_endpoints_and_package_dependencies(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "server" / "app.js",
        "const express = require('express');\n"
        "const app = express();\n"
        "app.post('/api/notes', async (_req, res) => res.json({ ok: true }));\n"
        "app.delete('/api/notes/:id', async (_req, res) => res.status(204).send());\n",
    )
    write_file(
        tmp_path / "package.json",
        "{\n"
        '  "dependencies": {\n'
        '    "express": "^4.19.2",\n'
        '    "sqlite3": "5.1.7"\n'
        "  },\n"
        '  "devDependencies": {\n'
        '    "vitest": "^1.6.0"\n'
        "  }\n"
        "}\n",
    )

    plugin = get_plugin_for_stack("express_node")
    assert plugin is not None
    bundle = plugin.collect(tmp_path)

    assert any(endpoint[2] == "POST" and endpoint[3] == "/api/notes" for endpoint in bundle.write_endpoints)
    assert any(endpoint[2] == "DELETE" and endpoint[3] == "/api/notes/:id" for endpoint in bundle.write_endpoints)
    assert all(endpoint[1] != "async" for endpoint in bundle.write_endpoints)

    violations = {(name, violation, scope) for _, name, _, _, violation, scope in bundle.dependency_specs}
    assert ("express", "range_not_pinned", "runtime") in violations
    assert ("sqlite3", None, "runtime") in violations
    assert ("vitest", "range_not_pinned", "development") in violations


def test_express_plugin_extracts_auth_middleware_boundaries(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "server" / "app.js",
        "const express = require('express');\n"
        "const app = express();\n"
        "app.post('/public/reset', (_req, res) => res.json({ ok: true }));\n"
        "app.use('/api', (req, res, next) => {\n"
        "  const token = req.header('x-session-token');\n"
        "  if (token !== 'demo') {\n"
        "    return res.status(401).json({ error: 'Unauthorized' });\n"
        "  }\n"
        "  next();\n"
        "});\n"
        "app.post('/api/notes', (_req, res) => res.json({ ok: true }));\n",
    )

    plugin = get_signal_plugin_for_stack("express_node")
    assert plugin is not None
    artifacts = plugin.collect(tmp_path)
    signals = plugin.collect_signals_from_artifacts(artifacts)

    protected = {
        row[1]
        for row in artifacts.authorization_boundaries
        if row[2] == "middleware"
    }
    assert "post_api_notes_11" in protected
    assert "post_public_reset_3" not in protected

    kinds = {signal.kind for signal in signals.signals}
    assert "authorization_boundary_enforced" in kinds


def test_express_plugin_extracts_integrity_session_and_html_safety_issues(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "server" / "services" / "notesService.js",
        "function mapRow(row) {\n"
        "  return { id: row.id, is_archived: row.is_archived };\n"
        "}\n"
        "async function createNote(input) {\n"
        "  const tagsCsv = String(input.tags || '').split('').join(',');\n"
        "  await db.run(`INSERT INTO notes (title, content, tags) VALUES (?, ?, ?)`, [input.content, input.title, tagsCsv]);\n"
        "}\n"
        "async function archiveNote(userId, id) {\n"
        "  await db.run(`UPDATE notes SET is_archived = 1 WHERE user_id = ?`, [userId]);\n"
        "}\n"
        "async function autosaveNote(userId, id, input) {\n"
        "  const clientUpdatedAt = input.updatedAt || new Date().toISOString();\n"
        "  await db.run(`UPDATE notes SET content = ?, updated_at = ? WHERE id = ? AND user_id = ?`, [input.content, clientUpdatedAt, id, userId]);\n"
        "}\n",
    )
    write_file(
        tmp_path / "public" / "app.js",
        "const state = { page: 1, limit: 5, total: 0 };\n"
        "function renderNotes(state, refs) {\n"
        "  refs.notesContainer.innerHTML = state.notes.map((note) => `<h3>${note.title}</h3><p>${note.archived}</p>`).join('');\n"
        "}\n"
        "async function loadNotes() {\n"
        "  const payload = await apiFetch('/api/notes?page=' + state.page + '&limit=' + state.limit);\n"
        "  state.total = payload.total;\n"
        "}\n"
        "async function handleCardClick(action) {\n"
        "  if (action === 'delete') {\n"
        "    await apiFetch('/api/notes/1', { method: 'DELETE' });\n"
        "    await loadNotes();\n"
        "  }\n"
        "}\n"
        "function updateSaveButtonState(title, content, refs) {\n"
        "  refs.saveBtn.disabled = !(title || content);\n"
        "}\n"
        "function login(payload) {\n"
        "  localStorage.setItem('sessionToken', payload.token);\n"
        "}\n"
        "function logout() {\n"
        "  localStorage.removeItem('session_token');\n"
        "}\n",
    )
    write_file(
        tmp_path / "public" / "styles.css",
        ".app {\n"
        "  min-width: 980px;\n"
        "}\n"
        "@media (max-width: 860px) {\n"
        "  .app { grid-template-columns: 1fr; }\n"
        "}\n",
    )
    write_file(
        tmp_path / "server" / "utils" / "noteMath.js",
        "function calculateReadingMinutes(content) {\n"
        "  const words = String(content || '').trim().split(/\\s+/).length;\n"
        "  return Math.round(words / 220);\n"
        "}\n"
        "function isOverdue(dueDate) {\n"
        "  return dueDate < new Date().toISOString();\n"
        "}\n"
        "function calculatePriorityScore({ pinned, lengthBoost, overdueBoost }) {\n"
        "  return Number((pinned ? 2 : 1 + lengthBoost + overdueBoost).toFixed(2));\n"
        "}\n",
    )

    plugin = get_signal_plugin_for_stack("express_node")
    assert plugin is not None
    artifacts = plugin.collect(tmp_path)
    signals = plugin.collect_signals_from_artifacts(artifacts)

    write_issue_types = {row[1] for row in artifacts.write_contract_issues}
    assert "char_split_normalization" in write_issue_types
    assert "db_insert_binding_mismatch" in write_issue_types
    assert "write_scope_missing_entity_filter" in write_issue_types
    assert "stale_write_without_conflict_guard" in write_issue_types
    assert "response_field_alias_mismatch" in write_issue_types
    assert "reading_time_rounding_floor_missing" in write_issue_types
    assert "priority_ternary_constant_branch" in write_issue_types
    assert "date_string_compare_with_iso" in write_issue_types

    session_issue_types = {row[1] for row in artifacts.session_lifecycle_issues}
    assert "storage_key_mismatch" in session_issue_types

    html_issue_types = {row[1] for row in artifacts.html_render_issues}
    assert "unsanitized_innerhtml" in html_issue_types

    ui_issue_types = {row[1] for row in artifacts.ui_ergonomics_issues}
    assert "pagination_page_not_normalized_after_mutation" in ui_issue_types
    assert "save_button_partial_form_enabled" in ui_issue_types
    assert "mobile_layout_min_width_overflow" in ui_issue_types

    kinds = {signal.kind for signal in signals.signals}
    assert "write_contract_integrity" in kinds
    assert "session_lifecycle_consistency" in kinds
    assert "html_render_safety" in kinds
    assert "ui_ergonomics" in kinds


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


def test_django_plugin_collects_viewset_routes_and_reverse_calls(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "views.py",
        "from rest_framework.viewsets import ViewSet\n"
        "from rest_framework.decorators import action\n"
        "from rest_framework.response import Response\n"
        "class OrderViewSet(ViewSet):\n"
        "    def create(self, request):\n"
        "        return Response({'status': 'created'})\n"
        "    @action(detail=True, methods=['post'], url_path='pay')\n"
        "    def pay(self, request, pk: str):\n"
        "        return Response({'id': pk, 'status': 'paid'})\n",
    )
    write_file(
        tmp_path / "app" / "urls.py",
        "from django.urls import include, path\n"
        "from rest_framework.routers import DefaultRouter\n"
        "from .views import OrderViewSet\n"
        "router = DefaultRouter()\n"
        "router.register('orders', OrderViewSet, basename='order')\n"
        "urlpatterns = [path('api/', include(router.urls))]\n",
    )
    write_file(
        tmp_path / "tests" / "test_order_viewset.py",
        "from django.urls import reverse\n"
        "def test_create_order(client):\n"
        "    response = client.post(reverse('order-list'))\n"
        "    assert response.status_code in {200, 201, 202}\n"
        "def test_pay_order(client):\n"
        "    pay_path = reverse('order-pay', kwargs={'id': 'ord_1'})\n"
        "    response = client.post(pay_path)\n"
        "    assert response.status_code in {200, 201, 202}\n",
    )

    plugin = get_plugin_for_stack("django_drf")
    assert plugin is not None
    bundle = plugin.collect(tmp_path)

    endpoints = {(row[1], row[2], row[3]) for row in bundle.write_endpoints}
    assert ("OrderViewSet.create", "POST", "/api/orders") in endpoints
    assert ("OrderViewSet.pay", "POST", "/api/orders/{id}/pay") in endpoints
    calls = {(row[1], row[2], row[3]) for row in bundle.test_http_calls}
    assert ("test_create_order", "POST", "/api/orders") in calls
    assert ("test_pay_order", "POST", "/api/orders/ord_1/pay") in calls


def test_django_plugin_collects_dependency_specs_from_requirements(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "views.py",
        "from rest_framework.views import APIView\n"
        "from rest_framework.response import Response\n"
        "class HealthView(APIView):\n"
        "    def post(self, request):\n"
        "        return Response({'ok': True})\n",
    )
    write_file(
        tmp_path / "app" / "urls.py",
        "from django.urls import path\n"
        "from .views import HealthView\n"
        "urlpatterns = [path('health/', HealthView.as_view(), name='health')]\n",
    )
    write_file(tmp_path / "requirements.txt", "Django==5.0.0\nrequests>=2.31.0\n")
    write_file(tmp_path / "requirements-dev.txt", "pytest>=8.0\n")

    plugin = get_plugin_for_stack("django_drf")
    assert plugin is not None
    bundle = plugin.collect(tmp_path)

    violations = {(name, violation, scope) for _, name, _, _, violation, scope in bundle.dependency_specs}
    assert ("django", None, "runtime") in violations
    assert ("requests", "range_not_pinned", "runtime") in violations
    assert ("pytest", "range_not_pinned", "development") in violations
