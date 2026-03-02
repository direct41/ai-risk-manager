from django.urls import reverse


def test_health_post(client):
    response = client.post(reverse("health"))
    assert response.status_code in {200, 201, 202}
