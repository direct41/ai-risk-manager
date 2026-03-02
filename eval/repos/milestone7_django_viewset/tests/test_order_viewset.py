from django.urls import reverse


def test_create_order(client):
    response = client.post(reverse("order-list"))
    assert response.status_code in {200, 201, 202}


def test_pay_order(client):
    pay_path = reverse("order-pay", kwargs={"id": "ord_42"})
    response = client.post(pay_path)
    assert response.status_code in {200, 201, 202}
