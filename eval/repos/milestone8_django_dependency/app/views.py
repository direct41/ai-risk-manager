from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    def post(self, request):
        return Response({"status": "ok"})
