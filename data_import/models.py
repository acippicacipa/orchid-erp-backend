from django.db import models
from django.contrib.auth.models import User
from common.models import BaseModel
import json
from django.conf import settings

class ImportTemplate(BaseModel):
    """
    Templates for different types of data imports
    """
    TEMPLATE_TYPES = [
        ('CUSTOMERS', 'Customers'),
        ('SUPPLIERS', 'Suppliers'),
        ('ITEMS', 'Items/Products'),
        ('INVENTORY', 'Initial Inventory'),
        ('CATEGORIES', 'Categories'),
        ('LOCATIONS', 'Locations'),
        ("USERS", "Users"),
        ("SALES_ORDERS", "Sales Orders"),
        ("INVOICES", "Invoices"),
        ("PAYMENTS", "Payments"),
        ("PURCHASE_ORDERS", "Purchase Orders"),
        ("BILLS", "Bills"),
        ("SUPPLIER_PAYMENTS", "Supplier Payments"),
        ("ACCOUNTS", "Accounts"),
        ("JOURNAL_ENTRIES", "Journal Entries"),
        ("JOURNAL_ITEMS", "Journal Items"),
        ("LEDGERS", "Ledgers"),
    ]
    
    name = models.CharField(max_length=100)
    template_type = models.CharField(max_length=20, choices=TEMPLATE_TYPES)
    description = models.TextField(blank=True, null=True)
    required_columns = models.JSONField(help_text="List of required column names")
    optional_columns = models.JSONField(default=list, help_text="List of optional column names")
    column_mappings = models.JSONField(default=dict, help_text="Mapping of Excel columns to model fields")
    validation_rules = models.JSONField(default=dict, help_text="Validation rules for each column")
    sample_file = models.FileField(upload_to='import_templates/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['name', 'template_type']
    
    def __str__(self):
        return f"{self.name} ({self.get_template_type_display()})"

class DataImport(BaseModel):
    """
    Track data import operations
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('VALIDATING', 'Validating'),
        ('VALID', 'Valid'),
        ('INVALID', 'Invalid'),
        ('IMPORTING', 'Importing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    template = models.ForeignKey(ImportTemplate, on_delete=models.PROTECT)
    file = models.FileField(upload_to='imports/')
    original_filename = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    invalid_rows = models.PositiveIntegerField(default=0)
    imported_rows = models.PositiveIntegerField(default=0)
    error_summary = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.original_filename} - {self.get_status_display()}"
    
    @property
    def success_rate(self):
        """Calculate success rate percentage"""
        if self.total_rows == 0:
            return 0
        return round((self.valid_rows / self.total_rows) * 100, 2)

class ImportError(models.Model):
    """
    Store detailed error information for import validation
    """
    ERROR_TYPES = [
        ('MISSING_COLUMN', 'Missing Required Column'),
        ('INVALID_FORMAT', 'Invalid Format'),
        ('DUPLICATE_VALUE', 'Duplicate Value'),
        ('FOREIGN_KEY_ERROR', 'Related Record Not Found'),
        ('VALIDATION_ERROR', 'Validation Error'),
        ('DATA_TYPE_ERROR', 'Data Type Error'),
    ]
    
    data_import = models.ForeignKey(DataImport, on_delete=models.CASCADE, related_name='errors')
    row_number = models.PositiveIntegerField()
    column_name = models.CharField(max_length=100, blank=True, null=True)
    error_type = models.CharField(max_length=20, choices=ERROR_TYPES)
    error_message = models.TextField()
    raw_value = models.TextField(blank=True, null=True)
    suggested_value = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['row_number', 'column_name']
    
    def __str__(self):
        return f"Row {self.row_number}: {self.error_message}"

class ImportLog(models.Model):
    """
    Detailed log of import operations
    """
    data_import = models.ForeignKey(DataImport, on_delete=models.CASCADE, related_name='logs')
    timestamp = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=10, choices=[
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
    ])
    message = models.TextField()
    details = models.JSONField(blank=True, null=True)
    
    class Meta:
        ordering = ['timestamp']
    
    def __str__(self):
        return f"{self.level}: {self.message[:50]}"

class ImportMapping(BaseModel):
    """
    Store user-defined column mappings for imports
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, # <-- UBAH INI
        on_delete=models.CASCADE
    )
    template = models.ForeignKey(ImportTemplate, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    column_mappings = models.JSONField(help_text="User's custom column mappings")
    is_default = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ['user', 'template', 'name']
    
    def __str__(self):
        return f"{self.user.username} - {self.name}"
