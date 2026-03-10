from fastapi import APIRouter, FastAPI

router = APIRouter()
app = FastAPI()


@router.post("/login")
def login(request) -> dict[str, bool]:
    request.session["sessionToken"] = "demo"
    return {"ok": True}


@router.post("/logout")
def logout(request) -> dict[str, bool]:
    request.session.pop("sessionToken", None)
    return {"ok": True}


app.include_router(router)
