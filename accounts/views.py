from django.shortcuts import render
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import get_user_model
from django.db import models, transaction
from rest_framework import status, generics, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from .models import UserProfile, UserRole
from .serializers import UserSerializer, UserProfileSerializer, UserRoleSerializer, UserUpdateSerializer, UserCreateSerializer

User = get_user_model()

class LoginView(APIView):
    """
    User login endpoint
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        
        if not username or not password:
            return Response({
                'error': 'Username and password are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = authenticate(username=username, password=password)
        
        if user:
            if user.is_active:
                login(request, user)
                token, created = Token.objects.get_or_create(user=user)
                
                # Get user profile if exists
                profile_data = {}
                profile = getattr(user, 'profile', None)

                # Cek jika profil ada DAN jika peran di dalam profil ada
                if profile and profile.role:
                    profile_data = {
                        'role': profile.role.name,
                        'role_display': profile.role.display_name,
                        'full_name': profile.full_name,
                        'employee_id': profile.employee_id,
                        'department': profile.department,
                    }
                else:
                    # Berikan nilai default jika profil atau peran tidak ada
                    profile_data = {
                        'role': None,
                        'role_display': 'No Role Assigned',
                        'full_name': user.get_full_name() or user.username,
                        'employee_id': None,
                        'department': None,
                    }
                
                return Response({
                    'message': 'Login successful',
                    'token': token.key,
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        **profile_data
                    }
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'error': 'Account is disabled'
                }, status=status.HTTP_401_UNAUTHORIZED)
        else:
            return Response({
                'error': 'Invalid credentials'
            }, status=status.HTTP_401_UNAUTHORIZED)

class LogoutView(APIView):
    """
    User logout endpoint
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            # Delete the user's token
            request.user.auth_token.delete()
        except:
            pass
        
        logout(request)
        return Response({
            'message': 'Logout successful'
        }, status=status.HTTP_200_OK)

class ProfileView(APIView):
    """
    Get current user profile
    """
    permission_classes = [IsAuthenticated] # Ini sudah benar
    
    def get(self, request):
        user = request.user
        profile_data = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
        }
        
        profile = getattr(user, 'profile', None)

        if profile:
            profile_data.update({
                # Cek jika role ada sebelum mengakses .name
                'role': profile.role.name if profile.role else None,
                'role_display': profile.role.display_name if profile.role else 'No Role Assigned',
                'employee_id': profile.employee_id,
                'department': profile.department,
                'position': profile.position,
                'hire_date': profile.hire_date,
                'is_active': profile.is_active,
            })
        else:
            # Berikan nilai default jika profil tidak ada sama sekali
            profile_data.update({
                'role': None,
                'role_display': 'No Profile',
                'employee_id': None,
                'department': None,
                'position': None,
                'hire_date': None,
                'is_active': False,
            })
        
        return Response(profile_data, status=status.HTTP_200_OK)

class UserViewSet(viewsets.ModelViewSet):
    """
    Complete User Management ViewSet with CRUD operations
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return UserCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserSerializer

    def get_queryset(self):
        # Check if user has admin role
        
        queryset = User.objects.select_related('profile__role').all()
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                models.Q(username__icontains=search) |
                models.Q(first_name__icontains=search) |
                models.Q(last_name__icontains=search) |
                models.Q(email__icontains=search)
            )
        return queryset.order_by('username')
    
    def perform_create(self, serializer):
        # Check admin permission
        try:
            if not self.request.user.profile.has_role('ADMIN'):
                raise PermissionError("Only administrators can create users")
        except UserProfile.DoesNotExist:
            raise PermissionError("Only administrators can create users")
        
        with transaction.atomic():
            # Create user
            user = serializer.save()
            
            # Create user profile if role is provided
            profile_data = self.request.data.get('profile', {})
            if profile_data:
                role_id = profile_data.get('role')
                if role_id:
                    try:
                        role = UserRole.objects.get(id=role_id)
                        UserProfile.objects.create(
                            user=user,
                            role=role,
                            employee_id=profile_data.get('employee_id'),
                            department=profile_data.get('department'),
                            position=profile_data.get('position'),
                            hire_date=profile_data.get('hire_date'),
                            is_active=profile_data.get('is_active', True)
                        )
                    except UserRole.DoesNotExist:
                        pass
    
    def perform_update(self, serializer):
        # Check admin permission
        try:
            if not self.request.user.profile.has_role('ADMIN'):
                raise PermissionError("Only administrators can update users")
        except UserProfile.DoesNotExist:
            raise PermissionError("Only administrators can update users")
        
        with transaction.atomic():
            user = serializer.save()
            
            # Update user profile if provided
            profile_data = self.request.data.get('profile', {})
            if profile_data:
                try:
                    profile = user.profile
                    role_id = profile_data.get('role')
                    if role_id:
                        try:
                            role = UserRole.objects.get(id=role_id)
                            profile.role = role
                        except UserRole.DoesNotExist:
                            pass
                    
                    profile.employee_id = profile_data.get('employee_id', profile.employee_id)
                    profile.department = profile_data.get('department', profile.department)
                    profile.position = profile_data.get('position', profile.position)
                    profile.hire_date = profile_data.get('hire_date', profile.hire_date)
                    profile.is_active = profile_data.get('is_active', profile.is_active)
                    profile.save()
                    
                except UserProfile.DoesNotExist:
                    # Create profile if it doesn't exist
                    role_id = profile_data.get('role')
                    if role_id:
                        try:
                            role = UserRole.objects.get(id=role_id)
                            UserProfile.objects.create(
                                user=user,
                                role=role,
                                employee_id=profile_data.get('employee_id'),
                                department=profile_data.get('department'),
                                position=profile_data.get('position'),
                                hire_date=profile_data.get('hire_date'),
                                is_active=profile_data.get('is_active', True)
                            )
                        except UserRole.DoesNotExist:
                            pass
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a user"""
        user = self.get_object()
        user.is_active = True
        user.save()
        
        try:
            profile = user.profile
            profile.is_active = True
            profile.save()
        except UserProfile.DoesNotExist:
            pass
        
        return Response({'message': 'User activated successfully'})
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate a user"""
        user = self.get_object()
        user.is_active = False
        user.save()
        
        try:
            profile = user.profile
            profile.is_active = False
            profile.save()
        except UserProfile.DoesNotExist:
            pass
        
        return Response({'message': 'User deactivated successfully'})
    
    @action(detail=True, methods=['post'])
    def reset_password(self, request, pk=None):
        """Reset user password"""
        user = self.get_object()
        new_password = request.data.get('password')
        
        if not new_password:
            return Response({'error': 'Password is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        user.set_password(new_password)
        user.save()
        
        return Response({'message': 'Password reset successfully'})

class UserRoleViewSet(viewsets.ReadOnlyModelViewSet):
    """
    User Role ViewSet for listing available roles
    """
    queryset = UserRole.objects.filter(is_active=True)
    serializer_class = UserRoleSerializer
    permission_classes = [AllowAny]

class UserListView(generics.ListAPIView):
    """
    List all users (admin only) - Legacy endpoint
    """
    queryset = User.objects.all()
    permission_classes = [AllowAny]
    
    def get(self, request):
        # Check if user has admin role
        try:
            if not request.user.profile.has_role('ADMIN'):
                return Response({
                    'error': 'Permission denied'
                }, status=status.HTTP_403_FORBIDDEN)
        except UserProfile.DoesNotExist:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        users = User.objects.all()
        users_data = []
        
        for user in users:
            user_data = {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'is_active': user.is_active,
                'date_joined': user.date_joined,
            }
            
            try:
                profile = user.profile
                user_data.update({
                    'role': profile.role.name,
                    'role_display': profile.role.display_name,
                    'employee_id': profile.employee_id,
                    'department': profile.department,
                })
            except UserProfile.DoesNotExist:
                user_data['role'] = None
                user_data['role_display'] = None
            
            users_data.append(user_data)
        
        return Response(users_data, status=status.HTTP_200_OK)
