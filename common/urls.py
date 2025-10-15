from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
# We'll add viewsets here later

urlpatterns = [
    path('', include(router.urls)),
    path('health/', views.HealthCheckView.as_view(), name='health-check'),
    path('system-info/', views.SystemInfoView.as_view(), name='system-info'),
]

