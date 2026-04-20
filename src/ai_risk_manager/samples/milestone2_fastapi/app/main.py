from enum import Enum

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

router = APIRouter()
app = FastAPI()


class OrderStatus(str, Enum):
    pending = "pending"
    paid = "paid"
    cancelled = "cancelled"


class OrderCreate(BaseModel):
    order_id: str


class OrderOut(BaseModel):
    order_id: str
    status: str


ALLOWED_TRANSITIONS = {
    "pending": ["paid", "cancelled"],
}


@router.post("/orders", response_model=OrderOut)
def create_order(payload: OrderCreate) -> OrderOut:
    return OrderOut(order_id=payload.order_id, status=OrderStatus.pending.value)


@router.post("/orders/{order_id}/pay", response_model=OrderOut)
def pay_order(order_id: str) -> OrderOut:
    status = "pending"
    if status == "pending":
        status = "paid"
    return OrderOut(order_id=order_id, status=status)


# No endpoint/handler currently performs pending -> cancelled.
app.include_router(router)
