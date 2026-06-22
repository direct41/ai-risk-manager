from __future__ import annotations

import ast
from pathlib import Path

import ai_risk_manager.rules.engine as rule_engine
from ai_risk_manager.collectors.plugins.base import ArtifactBundle, DataStoreWriteArtifact, ExternalCallArtifact
from ai_risk_manager.graph.builder import build_graph
from ai_risk_manager.pipeline.run import _filter_signals_to_impacted, run_pipeline
from ai_risk_manager.rules.architecture_policy import FROZEN_SIGNAL_ONLY_RULE_IDS, GRAPH_FIRST_RULE_IDS
from ai_risk_manager.rules.engine import run_rules
from ai_risk_manager.schemas.types import RunContext
from ai_risk_manager.signals.adapters import artifact_bundle_to_signal_bundle


def _write_flow_app(write_file, root: Path) -> None:
    write_file(
        root / "app" / "main.py",
        """from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
orders_db = {}

class PaymentGateway:
    def charge(self, order_id: str) -> None:
        pass

payment_gateway = PaymentGateway()

class PayRequest(BaseModel):
    order_id: str

ALLOWED_TRANSITIONS = {"pending": ["paid"]}

@router.post("/orders/{order_id}/pay")
def pay_order(payload: PayRequest):
    status = "pending"
    if status == "pending":
        status = "paid"
    orders_db[payload.order_id] = {"status": status}
    payment_gateway.charge(payload.order_id)
    return {"status": status}
""",
    )


def _run(root: Path, output_dir: Path):
    ctx = RunContext(
        repo_path=root,
        mode="full",
        base=None,
        output_dir=output_dir,
        provider="auto",
        no_llm=True,
    )
    result, code, _ = run_pipeline(ctx)
    assert code == 0
    assert result is not None
    return result


def test_complete_write_flow_requires_integration_or_e2e_coverage(tmp_path: Path, write_file) -> None:
    _write_flow_app(write_file, tmp_path)
    write_file(tmp_path / "tests" / "test_pay_order.py", "def test_pay_order_unit():\n    assert True\n")

    result = _run(tmp_path, tmp_path / ".riskmap")

    node_types = {node.type for node in result.graph.nodes}
    assert {"API", "Entity", "Transition", "DataStore", "ExternalSystem", "TestCase"}.issubset(node_types)
    edge_types = {edge.type for edge in result.graph.edges}
    assert {"covered_by", "triggers", "validated_by", "writes"}.issubset(edge_types)

    finding = next(row for row in result.findings.findings if row.rule_id == "critical_flow_no_integration_tests")
    assert finding.confidence == "high"
    plan_item = next(row for row in result.test_plan.items if row.finding_id == finding.id)
    assert plan_item.test_type == "integration"
    assert "external side effect" in plan_item.assertions[-1]

    entity_diagram = (tmp_path / ".riskmap" / "entity-relationships.mmd").read_text(encoding="utf-8")
    state_diagram = (tmp_path / ".riskmap" / "state-transitions.mmd").read_text(encoding="utf-8")
    assert "DataStore: orders_db" in entity_diagram
    assert "ExternalSystem: payment_gateway" in entity_diagram
    assert "pending" in state_diagram
    assert "paid" in state_diagram


def test_integration_http_coverage_clears_complete_write_flow_risk(tmp_path: Path, write_file) -> None:
    _write_flow_app(write_file, tmp_path)
    write_file(
        tmp_path / "tests" / "integration" / "test_pay_order.py",
        "def test_pay_order(client):\n    response = client.post('/orders/42/pay')\n    assert response.status_code == 200\n",
    )

    result = _run(tmp_path, tmp_path / ".riskmap")

    assert "critical_flow_no_integration_tests" not in {row.rule_id for row in result.findings.findings}
    test_node = next(node for node in result.graph.nodes if node.type == "TestCase")
    assert test_node.details["test_type"] == "integration"


def test_unused_nested_helper_does_not_add_architecture_effects(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "main.py",
        """from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
orders_db = {}
payment_gateway = object()

class Request(BaseModel):
    order_id: str

ALLOWED_TRANSITIONS = {"pending": ["paid"]}

@router.post("/orders/pay")
def pay_order(payload: Request):
    status = "pending"
    if status == "pending":
        status = "paid"
    def unused_helper():
        orders_db[payload.order_id] = {"status": status}
        payment_gateway.send(payload.order_id)
    return {"status": status}
""",
    )
    write_file(tmp_path / "tests" / "test_pay_order.py", "def test_pay_order():\n    assert True\n")

    result = _run(tmp_path, tmp_path / ".riskmap")

    assert not {"DataStore", "ExternalSystem"} & {node.type for node in result.graph.nodes}
    assert "critical_flow_no_integration_tests" not in {row.rule_id for row in result.findings.findings}


def test_ambiguous_handler_effect_stays_attached_to_api() -> None:
    graph = build_graph(
        ArtifactBundle(
            write_endpoints=[("app/api.py", "change_order", "POST", "/orders/change", 5, "endpoint")],
            handled_transitions=[
                ("app/api.py", "change_order", "pending", "paid", 10, "paid", True),
                ("app/api.py", "change_order", "pending", "cancelled", 12, "cancelled", True),
            ],
            data_store_writes=[
                DataStoreWriteArtifact("app/api.py", "change_order", "orders_db", "assign", 14, "write")
            ],
        )
    )

    write_edge = next(edge for edge in graph.edges if edge.type == "writes")
    assert write_edge.source_node_id.startswith("api:")


def test_impacted_signal_filter_preserves_unchanged_integration_coverage() -> None:
    signals = artifact_bundle_to_signal_bundle(
        ArtifactBundle(
            write_endpoints=[("app/api.py", "pay_order", "POST", "/orders/{order_id}/pay", 5, "endpoint")],
            endpoint_models=[("app/api.py", "pay_order", "PayRequest")],
            pydantic_models=[("app/api.py", "PayRequest")],
            handled_transitions=[("app/api.py", "pay_order", "pending", "paid", 10, "paid", True)],
            test_cases=[("tests/integration/test_pay.py", "test_pay_order", 5, "test")],
            test_http_calls=[
                ("tests/integration/test_pay.py", "test_pay_order", "POST", "/orders/42/pay", 6, "client.post")
            ],
            data_store_writes=[
                DataStoreWriteArtifact("app/api.py", "pay_order", "orders_db", "assign", 12, "write")
            ],
            external_calls=[
                ExternalCallArtifact("app/api.py", "pay_order", "payment_gateway", "charge", 13, "charge")
            ],
        )
    )

    impacted = _filter_signals_to_impacted(signals, {"app/api.py"})

    assert any(signal.source_ref.startswith("tests/integration/") for signal in impacted.signals)
    findings = run_rules(impacted)
    assert "critical_flow_no_integration_tests" not in {finding.rule_id for finding in findings.findings}


def test_all_rules_are_classified_by_graph_first_architecture_policy() -> None:
    engine_path = Path(rule_engine.__file__)
    tree = ast.parse(engine_path.read_text(encoding="utf-8"))
    implemented_rule_ids = {
        keyword.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "rule_id"
        and isinstance(keyword.value, ast.Constant)
        and isinstance(keyword.value.value, str)
    }

    assert implemented_rule_ids == GRAPH_FIRST_RULE_IDS | FROZEN_SIGNAL_ONLY_RULE_IDS
