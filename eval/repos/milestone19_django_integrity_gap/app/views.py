from rest_framework.response import Response
from rest_framework.viewsets import ViewSet


class NotesViewSet(ViewSet):
    def partial_update(self, request, pk=None):
        client_updated_at = request.data["updated_at"]
        Note.objects.filter(user_id=request.user.id).update(
            content=request.data["content"],
            updated_at=client_updated_at,
        )
        return Response({"ok": True})
