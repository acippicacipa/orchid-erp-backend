from django.db import models
from django.conf import settings

class BaseModel(models.Model):
    """
    Abstract base class that provides self-updating 'created_at' and 'updated_at' fields.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, # <-- Gunakan settings.AUTH_USER_MODEL
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_created_by"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, # <-- Gunakan settings.AUTH_USER_MODEL
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_updated_by"
    )

    class Meta:
        abstract = True
        ordering = ['-created_at']

class Address(BaseModel):
    """
    Address model for customers, suppliers, and company locations
    """
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default='Indonesia')
    
    class Meta:
        verbose_name_plural = "Addresses"
    
    def __str__(self):
        return f"{self.address_line_1}, {self.city}, {self.state}"

class Contact(BaseModel):
    """
    Contact information model
    """
    phone = models.CharField(max_length=20, blank=True, null=True)
    mobile = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    
    def __str__(self):
        return f"Phone: {self.phone}, Email: {self.email}"

class Company(BaseModel):
    """
    Company information model
    """
    name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=200, blank=True, null=True)
    tax_id = models.CharField(max_length=50, blank=True, null=True)
    registration_number = models.CharField(max_length=50, blank=True, null=True)
    address = models.OneToOneField(Address, on_delete=models.CASCADE, null=True, blank=True)
    contact = models.OneToOneField(Contact, on_delete=models.CASCADE, null=True, blank=True)
    logo = models.ImageField(upload_to='company/logos/', blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Companies"
    
    def __str__(self):
        return self.name

class Location(BaseModel):
    """
    Physical locations/warehouses for inventory management
    """
    LOCATION_TYPES = [
        ('WAREHOUSE', 'Main Warehouse'),
        ('ONLINE_STORE', 'Online Store'),
        ('OFFLINE_STORE', 'Offline Store'),
        ('PRODUCTION', 'Production Area'),
        ('QUALITY', 'Quality Control'),
        ('DAMAGED', 'Damaged Goods'),
    ]
    
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    location_type = models.CharField(max_length=20, choices=LOCATION_TYPES)
    address = models.OneToOneField(Address, on_delete=models.CASCADE, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.name} ({self.code})"

class Category(BaseModel):
    """
    Hierarchical category model for items
    """
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name_plural = "Categories"
        unique_together = ['name', 'parent']
    
    def __str__(self):
        if self.parent:
            return f"{self.parent.name} > {self.name}"
        return self.name
    
    @property
    def full_path(self):
        """Return the full category path"""
        path = [self.name]
        parent = self.parent
        while parent:
            path.insert(0, parent.name)
            parent = parent.parent
        return " > ".join(path)
