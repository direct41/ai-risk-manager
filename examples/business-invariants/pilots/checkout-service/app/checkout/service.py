def finalize_checkout(cart_total: int) -> dict[str, int | str]:
    return {"status": "paid", "total": cart_total}
