from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet


class OrderViewSet(ViewSet):
    def create(self, request):
        return Response({"status": "created"})

    @action(detail=True, methods=["post"], url_path="pay")
    def pay(self, request, pk: str):
        return Response({"id": pk, "status": "paid"})
