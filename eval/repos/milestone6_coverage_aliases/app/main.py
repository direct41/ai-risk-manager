from fastapi import APIRouter

router = APIRouter()


@router.post("/orders/{order_id}/pay")
def pay_order(order_id: str) -> dict[str, str]:
    return {"order_id": order_id, "status": "paid"}
