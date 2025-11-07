# dataimport/admin.py

from django.contrib import admin
# Pastikan hanya mengimpor model yang ada
from .models import ImportTemplate, DataImport, ImportErrorLog 

# Daftarkan model ImportTemplate agar bisa dikelola di admin
@admin.register(ImportTemplate)
class ImportTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'template_type', 'is_active', 'created_at')
    list_filter = ('template_type', 'is_active')
    search_fields = ('name', 'description')

# Inline admin untuk menampilkan log error langsung di halaman DataImport
class ImportErrorLogInline(admin.TabularInline):
    model = ImportErrorLog
    fields = ('row_number', 'error_message', 'raw_data')
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

@admin.register(DataImport)
class DataImportAdmin(admin.ModelAdmin):
    """
    Konfigurasi Admin untuk model DataImport yang sudah diperbaiki.
    """
    # Ganti 'import_type' dengan 'template'
    list_display = (
        'original_filename',
        'template', # <-- DIPERBAIKI
        'status',
        'uploaded_by',
        'successful_rows',
        'failed_rows',
        'created_at'
    )
    # Ganti 'import_type' dengan filter melalui relasi template
    list_filter = ('status', 'template__template_type', 'created_at') # <-- DIPERBAIKI
    search_fields = ('original_filename', 'uploaded_by__username', 'template__name')
    
    # Sesuaikan readonly_fields dengan model DataImport yang benar
    readonly_fields = (
        'template', # <-- DIPERBAIKI
        'created_at',
        'updated_at',
        'original_filename',
        'uploaded_by',
        'status',
        'total_rows',
        'processed_rows',
        'successful_rows',
        'failed_rows',
        'started_at',
        'completed_at',
        'notes',
        'file',
        # 'error_file' dihapus karena tidak ada di model
    )
    
    inlines = [ImportErrorLogInline]

    def has_add_permission(self, request):
        return False

    # Izinkan admin untuk mengubah status secara manual jika diperlukan untuk perbaikan
    # def has_change_permission(self, request, obj=None):
    #     return False

@admin.register(ImportErrorLog)
class ImportErrorLogAdmin(admin.ModelAdmin):
    """
    Konfigurasi Admin untuk model ImportErrorLog.
    """
    list_display = ('data_import', 'row_number', 'error_message')
    # Ganti filter agar sesuai dengan relasi yang benar
    list_filter = ('data_import__template__template_type',) # <-- DIPERBAIKI
    search_fields = ('data_import__original_filename', 'error_message', 'raw_data')
    
    readonly_fields = ('data_import', 'row_number', 'raw_data', 'error_message')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
