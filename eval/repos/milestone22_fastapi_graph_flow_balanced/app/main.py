from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

router = APIRouter()
app = FastAPI()


class DatabaseSession:
    def add(self, row: object) -> None:
        pass


class PaymentGateway:
    def charge(self, order_id: str) -> None:
        pass


class PayRequest(BaseModel):
    order_id: str


db = DatabaseSession()
payment_gateway = PaymentGateway()
ALLOWED_TRANSITIONS = {"pending": ["paid"]}


@router.post("/orders/{order_id}/pay")
def pay_order(payload: PayRequest) -> dict[str, str]:
    status = "pending"
    if status == "pending":
        status = "paid"
    db.add({"order_id": payload.order_id, "status": status})
    payment_gateway.charge(payload.order_id)
    return {"status": status}


app.include_router(router)
