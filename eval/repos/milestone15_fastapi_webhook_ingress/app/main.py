from fastapi import APIRouter, FastAPI

router = APIRouter()
app = FastAPI()


@router.post("/webhooks/stripe")
def stripe_webhook() -> dict[str, bool]:
    return {"accepted": True}


app.include_router(router)
