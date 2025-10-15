from django.shortcuts import render
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
import platform
import sys
from django.conf import settings

class HealthCheckView(APIView):
    """
    Health check endpoint
    """
    permission_classes = []  # Allow anonymous access
    
    def get(self, request):
        return Response({
            'status': 'healthy',
            'message': 'Orchid ERP API is running',
            'timestamp': '2024-01-01T00:00:00Z'
        }, status=status.HTTP_200_OK)

class SystemInfoView(APIView):
    """
    System information endpoint (admin only)
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # Check if user has admin role
        try:
            if not request.user.profile.has_role('ADMIN'):
                return Response({
                    'error': 'Permission denied'
                }, status=status.HTTP_403_FORBIDDEN)
        except:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        return Response({
            'system': {
                'platform': platform.platform(),
                'python_version': sys.version,
                'django_version': settings.DJANGO_VERSION if hasattr(settings, 'DJANGO_VERSION') else 'Unknown',
            },
            'database': {
                'engine': settings.DATABASES['default']['ENGINE'],
                'name': settings.DATABASES['default']['NAME'],
            },
            'debug': settings.DEBUG,
        }, status=status.HTTP_200_OK)
