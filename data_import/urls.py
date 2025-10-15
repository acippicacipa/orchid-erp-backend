from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
# We'll add viewsets here later

urlpatterns = [
    path('', include(router.urls)),
    path('upload/', views.DataUploadView.as_view(), name='data-upload'),
    path('validate/', views.DataValidationView.as_view(), name='data-validation'),
    path('import/', views.DataImportView.as_view(), name='data-import'),
    path('templates/', views.TemplateDownloadView.as_view(), name='template-download'),
    path('history/', views.ImportHistoryView.as_view(), name='import-history'),
    path('logs/', views.ImportLogsView.as_view(), name='import-logs'),
    path('setup-templates/', views.SetupTemplatesView.as_view(), name='setup-templates'),
]

