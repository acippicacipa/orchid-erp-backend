from django.urls import path, include
from rest_framework.routers import DefaultRouter

# Create a minimal router for now
router = DefaultRouter()

urlpatterns = [
    path('', include(router.urls)),
]
