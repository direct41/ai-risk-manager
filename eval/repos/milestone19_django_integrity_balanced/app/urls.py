from rest_framework.routers import DefaultRouter

from .views import NotesViewSet

router = DefaultRouter()
router.register("notes", NotesViewSet, basename="notes")

urlpatterns = router.urls
