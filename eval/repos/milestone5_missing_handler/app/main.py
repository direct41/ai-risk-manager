from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

router = APIRouter()
app = FastAPI()


class InvoiceCreate(BaseModel):
    invoice_id: str


class InvoiceOut(BaseModel):
    invoice_id: str
    status: str


ALLOWED_TRANSITIONS = {
    "draft": ["sent"],
    "sent": ["paid"],
}


@router.post('/invoices', response_model=InvoiceOut)
def create_invoice(payload: InvoiceCreate) -> InvoiceOut:
    return InvoiceOut(invoice_id=payload.invoice_id, status="draft")


@router.post('/invoices/{invoice_id}/send', response_model=InvoiceOut)
def send_invoice(invoice_id: str) -> InvoiceOut:
    status = "draft"
    if status == "draft":
        status = "sent"
    return InvoiceOut(invoice_id=invoice_id, status=status)


# Missing sent -> paid handler on purpose.
app.include_router(router)
