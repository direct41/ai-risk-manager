from app.checkout.service import finalize_checkout


def test_finalize_checkout() -> None:
    assert finalize_checkout(1200) == {"status": "paid", "total": 1200}
