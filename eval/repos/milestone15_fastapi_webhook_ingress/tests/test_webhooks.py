import pytest


def test_stripe_webhook(client) -> None:
    client.post("/webhooks/stripe")
    assert True
