from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

router = APIRouter()
app = FastAPI()


class OrderCreate(BaseModel):
    order_id: str


class OrderOut(BaseModel):
    order_id: str
    status: str


ALLOWED_TRANSITIONS = {
    "pending": ["paid", "cancelled"],
}


@router.post('/orders', response_model=OrderOut)
def create_order(payload: OrderCreate) -> OrderOut:
    return OrderOut(order_id=payload.order_id, status="pending")


@router.post('/orders/{order_id}/pay', response_model=OrderOut)
def pay_order(order_id: str) -> OrderOut:
    status = "pending"
    if status == "pending":
        status = "paid"
    return OrderOut(order_id=order_id, status=status)


@router.post('/orders/{order_id}/cancel', response_model=OrderOut)
def cancel_order(order_id: str) -> OrderOut:
    status = "pending"
    if status == "pending":
        status = "cancelled"
    return OrderOut(order_id=order_id, status=status)


app.include_router(router)
