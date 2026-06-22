import pytest  # noqa: F401


def test_pay_order(client) -> None:
    response = client.post("/orders/42/pay")
    assert response.status_code == 200
