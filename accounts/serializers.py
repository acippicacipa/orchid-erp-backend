from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from django.contrib.auth import get_user_model
from .models import UserProfile, UserRole

User = get_user_model()

class UserRoleSerializer(serializers.ModelSerializer):
    """Serializer for UserRole model"""
    class Meta:
        model = UserRole
        fields = ['id', 'name', 'display_name', 'description', 'is_active']

class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for UserProfile model"""
    # Field untuk MEMBACA (GET): Menampilkan nama peran.
    role_name = serializers.CharField(source='role.display_name', read_only=True)
    
    role_id = serializers.PrimaryKeyRelatedField(
        queryset=UserRole.objects.all(), 
        source='role', 
        write_only=True,
        allow_null=True,
        required=False
    )

    class Meta:
        model = UserProfile
        fields = [
            'id', 'employee_id', 'role', 'role_id', 'role_name', 'department', 
            'position', 'hire_date', 'is_active', 'notes'
        ]
        # --- PERUBAHAN KUNCI DI SINI ---
        # Jadikan 'employee_id' hanya bisa dibaca.
        # DRF akan otomatis mengabaikan field ini dari data input (POST/PUT/PATCH).
        read_only_fields = ['role', 'employee_id']
    
    
    def validate_employee_id(self, value):
        """
        Custom validation for employee_id to handle updates properly
        """
        if not value:
            return value

        # Get the current instance if this is an update operation.
        instance = getattr(self, 'instance', None)
        
        # Build the queryset to check for existing employee_id.
        queryset = UserProfile.objects.filter(employee_id=value)
        
        # If we are updating an existing instance, we must exclude it from the check.
        if instance:
            queryset = queryset.exclude(pk=instance.pk)
        
        # If any other profile with this employee_id exists, raise an error.
        if queryset.exists():
            raise serializers.ValidationError(
                "A user profile with this employee ID already exists."
            )
        
        return value

    # Your update method is fine, but it can be simplified.
    # The default ModelSerializer.update() already does this.
    # You can remove this method unless you have more complex logic to add.
    def update(self, instance, validated_data):
        """
        Override update method to handle profile updates properly.
        Note: This can be simplified.
        """
        # The parent class's update method handles this loop automatically.
        return super().update(instance, validated_data)

class UserSerializer(serializers.ModelSerializer):
    """Comprehensive User serializer with profile information"""
    profile = UserProfileSerializer(read_only=True)
    full_name = serializers.SerializerMethodField()
    role_display = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 
            'is_active', 'is_staff', 'date_joined', 'last_login',
            'password', 'profile', 'full_name', 'role_display'
        ]
        extra_kwargs = {
            'password': {'write_only': True},
            'email': {'required': False, 'allow_blank': True}
        }
    
    def get_full_name(self, obj):
        """Get user's full name"""
        return obj.get_full_name() or obj.username
    
    def get_role_display(self, obj):
        """Get user's role display name"""
        try:
            return obj.profile.role.display_name
        except (UserProfile.DoesNotExist, AttributeError):
            return None
    
    def create(self, validated_data):
        """Create user with password hashing"""
        password = validated_data.pop('password', None)
        user = User.objects.create(**validated_data)
        
        if password:
            user.set_password(password)
            user.save()
        
        return user
    
    def update(self, instance, validated_data):
        """Update user with password hashing"""
        password = validated_data.pop('password', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if password:
            instance.set_password(password)
        
        instance.save()
        return instance

class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating users with profile data"""
    profile = UserProfileSerializer(required=False)
    password = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'first_name', 'last_name', 
            'is_active', 'is_staff', 'password', 'profile'
        ]

        extra_kwargs = {
            'email': {'required': False, 'allow_blank': True}
        }
    
    def create(self, validated_data):
        """
        Membuat user beserta profilnya dengan aman.
        """
        profile_data = validated_data.pop('profile', {})
        password = validated_data.pop('password')
        
        # Langkah 1: Buat user seperti biasa
        user = User.objects.create(**validated_data)
        user.set_password(password)
        user.save()
        
        # --- PERUBAHAN KUNCI DI SINI ---
        # Langkah 2: Dapatkan atau buat profil, lalu update datanya.
        # Ini cara yang paling aman (defensif).
        
        # `user.profile` akan error jika profil belum ada, jadi kita gunakan try-except
        # atau cara yang lebih baik: UserProfile.objects.get_or_create()
        
        profile, created = UserProfile.objects.get_or_create(
            user=user,
            defaults=profile_data  # <--- INI BAGIAN PENTINGNYA
        )
        
        # Jika profil TIDAK baru dibuat (misalnya oleh signal),
        # kita tetap perlu mengupdate datanya.
        if not created and profile_data:
            # Loop melalui data dan update instance profil
            for attr, value in profile_data.items():
                setattr(profile, attr, value)
            
            # Panggil save() untuk menyimpan perubahan dan juga men-trigger
            # logika employee_id jika kebetulan kosong.
            profile.save()

        # Refresh user instance untuk mendapatkan data profil terbaru
        user.refresh_from_db()
        return user

class UserUpdateSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(required=False)
    password = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'first_name', 'last_name', 
            'is_active', 'is_staff', 'password', 'profile'
        ]

        extra_kwargs = {
            'email': {'required': False, 'allow_blank': True}
        }
    
    def update(self, instance, validated_data):
        """Update user with profile"""
        profile_data = validated_data.pop('profile', None)
        password = validated_data.pop('password', None)
        
        request = self.context.get('request')
        current_user = request.user if request and hasattr(request, 'user') else None

        # Update user fields
        instance = super().update(instance, validated_data)
        
        if password:
            instance.set_password(password)
            instance.save()

        # Update or create profile
        if profile_data:
            profile = instance.profile  # Asumsikan profil sudah ada.

            # Loop melalui data profil dan update setiap field.
            # Ini lebih dinamis daripada menyebutkan setiap field satu per satu.
            for attr, value in profile_data.items():
                setattr(profile, attr, value)
            
            # Jangan lupa untuk mengisi updated_by
            request = self.context.get('request')
            if request and hasattr(request, 'user'):
                profile.updated_by = request.user

            profile.save()

        return instance