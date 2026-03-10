from rest_framework.decorators import api_view


@api_view(["POST"])
def login(request):
    request.session["sessionToken"] = "demo"
    return {"ok": True}


@api_view(["POST"])
def logout(request):
    request.session.pop("session_token", None)
    return {"ok": True}
