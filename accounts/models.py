from django.db import models
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from .managers import CustomUserManager
from common.models import BaseModel, Contact
import datetime
from django.contrib.auth.models import AbstractUser
from django.conf import settings

class User(AbstractUser):
    # Override field email untuk membuatnya tidak unik dan boleh kosong
    email = models.EmailField(blank=True, unique=False) # <-- Perubahan utama

    # Ganti USERNAME_FIELD jika Anda ingin login dengan field lain
    # USERNAME_FIELD = 'username' (ini default, tidak perlu diubah)

    # Beritahu Django untuk menggunakan manager kustom kita
    objects = CustomUserManager()

    def __str__(self):
        return self.username

class UserRole(models.Model):
    """
    Predefined roles for the ERP system
    """
    ROLE_CHOICES = [
        ('ADMIN', 'Administrator'),
        ('SALES', 'Sales'),
        ('WAREHOUSE', 'Warehouse'),
        ('AUDIT', 'Audit'),
        ('PURCHASING', 'Purchasing'),
        ('ACCOUNTING', 'Accounting'),
    ]
    
    name = models.CharField(max_length=20, choices=ROLE_CHOICES, unique=True)
    display_name = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)
    permissions = models.ManyToManyField(Permission, blank=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.display_name
    
    @classmethod
    def create_default_roles(cls):
        """Create default roles with appropriate permissions"""
        roles_data = [
            {
                'name': 'ADMIN',
                'display_name': 'Administrator',
                'description': 'Full system access and user management'
            },
            {
                'name': 'SALES',
                'display_name': 'Sales',
                'description': 'Sales orders, customer management, and reporting'
            },
            {
                'name': 'WAREHOUSE',
                'display_name': 'Warehouse',
                'description': 'Inventory management, stock movements, and goods receipt'
            },
            {
                'name': 'AUDIT',
                'display_name': 'Audit',
                'description': 'Read-only access to all modules for auditing purposes'
            },
            {
                'name': 'PURCHASING',
                'display_name': 'Purchasing',
                'description': 'Purchase orders, supplier management, and procurement'
            },
            {
                'name': 'ACCOUNTING',
                'display_name': 'Accounting',
                'description': 'Financial management, invoicing, and accounting reports'
            },
        ]
        
        for role_data in roles_data:
            role, created = cls.objects.get_or_create(
                name=role_data['name'],
                defaults={
                    'display_name': role_data['display_name'],
                    'description': role_data['description']
                }
            )

class UserProfile(BaseModel):
    """
    Extended user profile for ERP system
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    employee_id = models.CharField(
        max_length=20, 
        unique=True, 
        blank=True, # Diizinkan kosong sementara sebelum disimpan
        editable=False
    )
    role = models.ForeignKey(UserRole, on_delete=models.PROTECT, null=True, blank=True)
    contact = models.OneToOneField(Contact, on_delete=models.CASCADE, null=True, blank=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    position = models.CharField(max_length=100, blank=True, null=True)
    hire_date = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    def __str__(self):
        role_display = self.role.display_name if self.role else "No Role"
        return f"{self.user.get_full_name() or self.user.username} ({role_display})"

    def _generate_employee_id(self):
        """
        Membuat ID Karyawan unik berdasarkan tahun dan ID user.
        Contoh: 20250042
        """
        current_year = datetime.date.today().year
        # Menggunakan user.pk sebagai nomor unik, di-padding dengan nol di kiri (total 4 digit)
        user_pk_padded = str(self.user.pk).zfill(4) 
        return f"{current_year}{user_pk_padded}"

    # --- OVERRIDE METHOD SAVE ---
    def save(self, *args, **kwargs):
        """
        Override method save untuk membuat employee_id secara otomatis
        saat profil pertama kali dibuat.
        """
        # Cek jika employee_id masih kosong. Ini akan true saat objek baru dibuat.
        if not self.employee_id:
            # Pastikan user sudah ada untuk mendapatkan `pk`-nya
            if self.user_id is None:
                # Jika user belum ada, simpan dulu objeknya agar user ter-link
                # dan kita bisa mendapatkan `self.user_id`.
                # Ini jarang terjadi jika Anda membuat UserProfile setelah User.
                super().save(*args, **kwargs)
            
            self.employee_id = self._generate_employee_id()
            # Hapus `force_insert` jika ada, agar bisa update field employee_id
            kwargs.pop('force_insert', None)

        super().save(*args, **kwargs)
    
    @property
    def full_name(self):
        return self.user.get_full_name() or self.user.username
    
    def has_role(self, role_name):
        """Check if user has a specific role"""
        return self.role.name == role_name
    
    def has_any_role(self, role_names):
        """Check if user has any of the specified roles"""
        return self.role.name in role_names

class UserSession(models.Model):
    """
    Track user sessions for security and auditing
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sessions')
    session_key = models.CharField(max_length=40, unique=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    login_time = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.login_time}"

class AuditLog(models.Model):
    """
    Audit log for tracking user actions
    """
    ACTION_CHOICES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('VIEW', 'View'),
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('EXPORT', 'Export'),
        ('IMPORT', 'Import'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    object_repr = models.CharField(max_length=200, blank=True)
    changes = models.JSONField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.user} - {self.action} - {self.timestamp}"
