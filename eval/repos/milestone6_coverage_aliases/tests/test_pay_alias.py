import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def pay_path() -> str:
    order_id = "ord_42"
    return f"/orders/{order_id}/pay"


def test_pay_order(client: TestClient, pay_path: str) -> None:
    path_alias = pay_path
    response = client.post(path_alias)
    assert response.status_code in {200, 201, 202}
