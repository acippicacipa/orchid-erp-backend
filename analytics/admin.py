from django.contrib import admin
from .models import (
    KPICategory, KPIDefinition, KPIValue, 
    ReportTemplate, ReportExecution
)


@admin.register(KPICategory)
class KPICategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'description']


@admin.register(KPIDefinition)
class KPIDefinitionAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'kpi_type', 'frequency', 'is_active']
    list_filter = ['category', 'kpi_type', 'frequency', 'is_active']
    search_fields = ['name', 'description']


@admin.register(KPIValue)
class KPIValueAdmin(admin.ModelAdmin):
    list_display = ['kpi', 'period_start', 'period_end', 'value', 'status']
    list_filter = ['kpi', 'status', 'period_start']
    search_fields = ['kpi__name']


@admin.register(ReportTemplate)
class ReportTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'report_type', 'is_active', 'is_public']
    list_filter = ['category', 'report_type', 'is_active', 'is_public']
    search_fields = ['name', 'description']


@admin.register(ReportExecution)
class ReportExecutionAdmin(admin.ModelAdmin):
    list_display = ['template', 'status', 'executed_by']
    list_filter = ['status', 'template']
    search_fields = ['template__name', 'executed_by__username']
