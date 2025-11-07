# dataimport/models.py

from django.db import models
from django.conf import settings
from common.models import BaseModel
import json

class ImportTemplate(BaseModel):
    """
    Templates for different types of data imports
    """
    TEMPLATE_TYPES = [
        ('CUSTOMERS', 'Customers'),
        ('SUPPLIERS', 'Suppliers'),
        ('PRODUCTS', 'Products'),
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
    # column_mappings = models.JSONField(default=dict, help_text="Mapping of Excel columns to model fields")
    # validation_rules = models.JSONField(default=dict, help_text="Validation rules for each column")
    # sample_file = models.FileField(upload_to='import_templates/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        # unique_together = ['name', 'template_type']
        db_table = "data_import_importtemplate"
        verbose_name = "Import Template"
        verbose_name_plural = "Import Templates"
    
    def __str__(self):
        return f"{self.name} ({self.get_template_type_display()})"

class DataImport(BaseModel):
    """
    Model untuk melacak setiap sesi operasi impor data.
    Setiap file yang diunggah untuk diimpor akan membuat satu record di sini.
    """
    
    # Menambahkan tipe impor yang lebih spesifik sesuai dengan model di 'inventory'
    IMPORT_TYPES = [
        ('PRODUCTS', 'Products'),
        ('CATEGORIES', 'Categories'),
        ('LOCATIONS', 'Locations'),
        ('STOCK_LEVELS', 'Stock Levels'),
        ('BOM', 'Bill of Materials (BOM)'),
        ('SUPPLIERS', 'Suppliers'),
        ('CUSTOMERS', 'Customers'),
        ('INVENTORY', 'Inventory'),
        # Tambahkan tipe lain sesuai kebutuhan
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('VALIDATING', 'Validating'),
        ('PROCESSING', 'Processing'), # Mengganti 'IMPORTING' agar lebih umum
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('COMPLETED_WITH_ERRORS', 'Completed with Errors'), # Status baru untuk kasus impor sebagian berhasil
    ]
    
    # Tipe data yang diimpor, dipilih dari choices di atas
    template = models.ForeignKey(
        ImportTemplate, 
        on_delete=models.PROTECT, # Mencegah template terhapus jika masih digunakan oleh sebuah import
        related_name='data_imports',
        help_text="Template yang digunakan untuk proses impor ini."
    )
    
    # File yang diunggah
    file = models.FileField(upload_to='imports/%Y/%m/')
    original_filename = models.CharField(max_length=255)
    
    # Pengguna yang melakukan impor
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='data_imports'
    )
    
    # Status proses impor
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    
    # Statistik hasil impor
    total_rows = models.PositiveIntegerField(default=0)
    processed_rows = models.PositiveIntegerField(default=0)
    successful_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)
    
    # Waktu pemrosesan
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Catatan atau ringkasan dari proses impor
    notes = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Data Import"
        verbose_name_plural = "Data Imports"
        db_table = "data_import_dataimport"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Import '{self.original_filename}' using template '{self.template.name}'"

    @property
    def duration(self):
        """Menghitung durasi proses impor."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None

# class ImportError(models.Model):
#     """
#     Store detailed error information for import validation
#     """
#     ERROR_TYPES = [
#         ('MISSING_COLUMN', 'Missing Required Column'),
#         ('INVALID_FORMAT', 'Invalid Format'),
#         ('DUPLICATE_VALUE', 'Duplicate Value'),
#         ('FOREIGN_KEY_ERROR', 'Related Record Not Found'),
#         ('VALIDATION_ERROR', 'Validation Error'),
#         ('DATA_TYPE_ERROR', 'Data Type Error'),
#     ]
    
#     data_import = models.ForeignKey(DataImport, on_delete=models.CASCADE, related_name='errors')
#     row_number = models.PositiveIntegerField()
#     column_name = models.CharField(max_length=100, blank=True, null=True)
#     error_type = models.CharField(max_length=20, choices=ERROR_TYPES)
#     error_message = models.TextField()
#     raw_value = models.TextField(blank=True, null=True)
#     suggested_value = models.TextField(blank=True, null=True)
    
#     class Meta:
#         ordering = ['row_number', 'column_name']
    
#     def __str__(self):
#         return f"Row {self.row_number}: {self.error_message}"

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

class ImportErrorLog(models.Model):
    data_import = models.ForeignKey(DataImport, on_delete=models.CASCADE, related_name='error_logs')
    row_number = models.PositiveIntegerField(help_text="Nomor baris di file asli yang error.")
    error_message = models.TextField()
    raw_data = models.JSONField(help_text="Data asli dari baris yang gagal.", null=True)

    class Meta:
        db_table = "data_import_importerrorlog"
        verbose_name = "Import Error Log"
        verbose_name_plural = "Import Error Logs"
        ordering = ['data_import', 'row_number']

    def __str__(self):
        return f"Error on row {self.row_number} for import ID: {self.data_import.id}"

