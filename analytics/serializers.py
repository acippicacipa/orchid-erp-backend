"""
Analytics Serializers for Orchid ERP Reporting & Business Intelligence
Provides API serialization for analytics models and data
"""

from rest_framework import serializers
from .models import (
    KPICategory, KPIDefinition, KPIValue, ReportTemplate, ReportExecution,
    Dashboard, DataSource, BusinessMetric, AlertRule, AlertInstance
)


class KPICategorySerializer(serializers.ModelSerializer):
    kpis_count = serializers.SerializerMethodField()
    
    class Meta:
        model = KPICategory
        fields = '__all__'
    
    def get_kpis_count(self, obj):
        return obj.kpis.filter(is_active=True).count()


class KPIDefinitionSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    latest_value = serializers.SerializerMethodField()
    trend = serializers.SerializerMethodField()
    
    class Meta:
        model = KPIDefinition
        fields = '__all__'
    
    def get_latest_value(self, obj):
        latest = obj.values.first()
        if latest:
            return {
                'value': latest.value,
                'formatted_value': f"{latest.value} {obj.unit}".strip(),
                'status': latest.status,
                'period_start': latest.period_start,
                'period_end': latest.period_end,
                'variance': latest.variance,
                'variance_percentage': latest.variance_percentage,
            }
        return None
    
    def get_trend(self, obj):
        """Get trend data for the last 12 periods"""
        values = obj.values.order_by('-period_start')[:12]
        return [
            {
                'period': value.period_start.strftime('%Y-%m-%d'),
                'value': value.value,
                'status': value.status,
            }
            for value in reversed(values)
        ]


class KPIValueSerializer(serializers.ModelSerializer):
    kpi_name = serializers.CharField(source='kpi.name', read_only=True)
    kpi_code = serializers.CharField(source='kpi.code', read_only=True)
    kpi_unit = serializers.CharField(source='kpi.unit', read_only=True)
    formatted_value = serializers.SerializerMethodField()
    
    class Meta:
        model = KPIValue
        fields = '__all__'
    
    def get_formatted_value(self, obj):
        return f"{obj.value} {obj.kpi.unit}".strip()


class ReportTemplateSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    executions_count = serializers.SerializerMethodField()
    last_execution = serializers.SerializerMethodField()
    
    class Meta:
        model = ReportTemplate
        fields = '__all__'
    
    def get_executions_count(self, obj):
        return obj.executions.count()
    
    def get_last_execution(self, obj):
        last_exec = obj.executions.first()
        if last_exec:
            return {
                'id': last_exec.id,
                'status': last_exec.status,
                'created_at': last_exec.created_at,
                'completed_at': last_exec.completed_at,
                'executed_by': last_exec.executed_by.get_full_name() if last_exec.executed_by else None,
            }
        return None


class ReportExecutionSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source='template.name', read_only=True)
    executed_by_name = serializers.CharField(source='executed_by.get_full_name', read_only=True)
    duration_seconds = serializers.SerializerMethodField()
    file_size_mb = serializers.SerializerMethodField()
    
    class Meta:
        model = ReportExecution
        fields = '__all__'
    
    def get_duration_seconds(self, obj):
        if obj.execution_time:
            return obj.execution_time.total_seconds()
        return None
    
    def get_file_size_mb(self, obj):
        if obj.file_size:
            return round(obj.file_size / (1024 * 1024), 2)
        return None


class DashboardSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    widgets_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Dashboard
        fields = '__all__'
    
    def get_widgets_count(self, obj):
        return len(obj.widgets) if obj.widgets else 0


class DataSourceSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    connection_status = serializers.SerializerMethodField()
    
    class Meta:
        model = DataSource
        fields = '__all__'
    
    def get_connection_status(self, obj):
        # In a real implementation, this would test the connection
        return 'connected' if obj.is_active else 'disconnected'


class BusinessMetricSerializer(serializers.ModelSerializer):
    formatted_value = serializers.SerializerMethodField()
    
    class Meta:
        model = BusinessMetric
        fields = '__all__'
    
    def get_formatted_value(self, obj):
        if obj.unit == 'IDR':
            return f"Rp {obj.value:,.0f}"
        elif obj.unit == '%':
            return f"{obj.value:.2f}%"
        else:
            return f"{obj.value} {obj.unit}".strip()


class AlertRuleSerializer(serializers.ModelSerializer):
    kpi_name = serializers.CharField(source='kpi.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    active_instances_count = serializers.SerializerMethodField()
    
    class Meta:
        model = AlertRule
        fields = '__all__'
    
    def get_active_instances_count(self, obj):
        return obj.instances.filter(status='ACTIVE').count()


class AlertInstanceSerializer(serializers.ModelSerializer):
    rule_name = serializers.CharField(source='rule.name', read_only=True)
    acknowledged_by_name = serializers.CharField(source='acknowledged_by.get_full_name', read_only=True)
    age_hours = serializers.SerializerMethodField()
    
    class Meta:
        model = AlertInstance
        fields = '__all__'
    
    def get_age_hours(self, obj):
        from django.utils import timezone
        delta = timezone.now() - obj.created_at
        return round(delta.total_seconds() / 3600, 1)


# Custom serializers for analytics data

class SalesAnalyticsSerializer(serializers.Serializer):
    """Serializer for sales analytics data"""
    total_sales_orders = serializers.IntegerField()
    total_sales_value = serializers.DecimalField(max_digits=15, decimal_places=2)
    average_order_value = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_invoices = serializers.IntegerField()
    total_invoice_value = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_payments = serializers.IntegerField()
    total_payment_value = serializers.DecimalField(max_digits=15, decimal_places=2)
    unique_customers = serializers.IntegerField()
    new_customers = serializers.IntegerField()
    
    # Formatted fields for display
    total_sales_value_formatted = serializers.SerializerMethodField()
    average_order_value_formatted = serializers.SerializerMethodField()
    total_invoice_value_formatted = serializers.SerializerMethodField()
    total_payment_value_formatted = serializers.SerializerMethodField()
    
    def get_total_sales_value_formatted(self, obj):
        return f"Rp {obj['total_sales_value']:,.0f}"
    
    def get_average_order_value_formatted(self, obj):
        return f"Rp {obj['average_order_value']:,.0f}"
    
    def get_total_invoice_value_formatted(self, obj):
        return f"Rp {obj['total_invoice_value']:,.0f}"
    
    def get_total_payment_value_formatted(self, obj):
        return f"Rp {obj['total_payment_value']:,.0f}"


class PurchasingAnalyticsSerializer(serializers.Serializer):
    """Serializer for purchasing analytics data"""
    total_purchase_orders = serializers.IntegerField()
    total_purchase_value = serializers.DecimalField(max_digits=15, decimal_places=2)
    average_purchase_value = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_bills = serializers.IntegerField()
    total_bill_value = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_supplier_payments = serializers.IntegerField()
    total_payment_value = serializers.DecimalField(max_digits=15, decimal_places=2)
    unique_suppliers = serializers.IntegerField()
    new_suppliers = serializers.IntegerField()
    
    # Formatted fields
    total_purchase_value_formatted = serializers.SerializerMethodField()
    average_purchase_value_formatted = serializers.SerializerMethodField()
    total_bill_value_formatted = serializers.SerializerMethodField()
    total_payment_value_formatted = serializers.SerializerMethodField()
    
    def get_total_purchase_value_formatted(self, obj):
        return f"Rp {obj['total_purchase_value']:,.0f}"
    
    def get_average_purchase_value_formatted(self, obj):
        return f"Rp {obj['average_purchase_value']:,.0f}"
    
    def get_total_bill_value_formatted(self, obj):
        return f"Rp {obj['total_bill_value']:,.0f}"
    
    def get_total_payment_value_formatted(self, obj):
        return f"Rp {obj['total_payment_value']:,.0f}"


class InventoryAnalyticsSerializer(serializers.Serializer):
    """Serializer for inventory analytics data"""
    total_products = serializers.IntegerField()
    total_inventory_value = serializers.DecimalField(max_digits=15, decimal_places=2)
    stock_movements_count = serializers.IntegerField()
    stock_movements_in = serializers.IntegerField()
    stock_movements_out = serializers.IntegerField()
    net_stock_change = serializers.IntegerField()
    low_stock_products = serializers.IntegerField()
    out_of_stock_products = serializers.IntegerField()
    
    # Formatted fields
    total_inventory_value_formatted = serializers.SerializerMethodField()
    
    def get_total_inventory_value_formatted(self, obj):
        return f"Rp {obj['total_inventory_value']:,.0f}"


class FinancialAnalyticsSerializer(serializers.Serializer):
    """Serializer for financial analytics data"""
    total_assets = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_liabilities = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_equity = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_revenue = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_expenses = serializers.DecimalField(max_digits=15, decimal_places=2)
    net_income = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_cash = serializers.DecimalField(max_digits=15, decimal_places=2)
    journal_entries_count = serializers.IntegerField()
    profit_margin = serializers.DecimalField(max_digits=5, decimal_places=2)
    return_on_assets = serializers.DecimalField(max_digits=5, decimal_places=2)
    
    # Formatted fields
    total_assets_formatted = serializers.SerializerMethodField()
    total_liabilities_formatted = serializers.SerializerMethodField()
    total_equity_formatted = serializers.SerializerMethodField()
    total_revenue_formatted = serializers.SerializerMethodField()
    total_expenses_formatted = serializers.SerializerMethodField()
    net_income_formatted = serializers.SerializerMethodField()
    total_cash_formatted = serializers.SerializerMethodField()
    profit_margin_formatted = serializers.SerializerMethodField()
    return_on_assets_formatted = serializers.SerializerMethodField()
    
    def get_total_assets_formatted(self, obj):
        return f"Rp {obj['total_assets']:,.0f}"
    
    def get_total_liabilities_formatted(self, obj):
        return f"Rp {obj['total_liabilities']:,.0f}"
    
    def get_total_equity_formatted(self, obj):
        return f"Rp {obj['total_equity']:,.0f}"
    
    def get_total_revenue_formatted(self, obj):
        return f"Rp {obj['total_revenue']:,.0f}"
    
    def get_total_expenses_formatted(self, obj):
        return f"Rp {obj['total_expenses']:,.0f}"
    
    def get_net_income_formatted(self, obj):
        return f"Rp {obj['net_income']:,.0f}"
    
    def get_total_cash_formatted(self, obj):
        return f"Rp {obj['total_cash']:,.0f}"
    
    def get_profit_margin_formatted(self, obj):
        return f"{obj['profit_margin']:.2f}%"
    
    def get_return_on_assets_formatted(self, obj):
        return f"{obj['return_on_assets']:.2f}%"


class DashboardDataSerializer(serializers.Serializer):
    """Serializer for dashboard summary data"""
    sales_analytics = SalesAnalyticsSerializer()
    purchasing_analytics = PurchasingAnalyticsSerializer()
    inventory_analytics = InventoryAnalyticsSerializer()
    financial_analytics = FinancialAnalyticsSerializer()
    
    # Top-level KPIs
    key_metrics = serializers.DictField()
    recent_alerts = AlertInstanceSerializer(many=True)
    trending_kpis = KPIValueSerializer(many=True)


class ReportBuilderFieldSerializer(serializers.Serializer):
    """Serializer for report builder field definitions"""
    name = serializers.CharField()
    label = serializers.CharField()
    type = serializers.ChoiceField(choices=[
        ('string', 'Text'),
        ('number', 'Number'),
        ('decimal', 'Decimal'),
        ('date', 'Date'),
        ('datetime', 'Date Time'),
        ('boolean', 'Boolean'),
    ])
    table = serializers.CharField()
    description = serializers.CharField(required=False)
    aggregatable = serializers.BooleanField(default=False)
    filterable = serializers.BooleanField(default=True)
    sortable = serializers.BooleanField(default=True)


class ReportBuilderTableSerializer(serializers.Serializer):
    """Serializer for report builder table definitions"""
    name = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField(required=False)
    fields = ReportBuilderFieldSerializer(many=True)
    relationships = serializers.DictField(required=False)


class CustomReportSerializer(serializers.Serializer):
    """Serializer for custom report requests"""
    name = serializers.CharField()
    description = serializers.CharField(required=False)
    tables = serializers.ListField(child=serializers.CharField())
    fields = serializers.ListField(child=serializers.CharField())
    filters = serializers.DictField(required=False)
    grouping = serializers.ListField(child=serializers.CharField(), required=False)
    sorting = serializers.ListField(child=serializers.DictField(), required=False)
    output_format = serializers.ChoiceField(
        choices=['JSON', 'CSV', 'EXCEL', 'PDF'],
        default='JSON'
    )
    chart_config = serializers.DictField(required=False)
