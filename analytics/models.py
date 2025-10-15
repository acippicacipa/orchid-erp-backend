"""
Analytics Models for Orchid ERP Reporting & Business Intelligence
Provides comprehensive data aggregation, KPI tracking, and report generation
"""

from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
import json


class KPICategory(models.Model):
    """Categories for organizing KPIs"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=7, default='#3B82F6')  # Hex color
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "KPI Categories"
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class KPIDefinition(models.Model):
    """Defines Key Performance Indicators"""
    
    KPI_TYPES = [
        ('FINANCIAL', 'Financial'),
        ('OPERATIONAL', 'Operational'),
        ('SALES', 'Sales'),
        ('INVENTORY', 'Inventory'),
        ('PURCHASING', 'Purchasing'),
        ('MANUFACTURING', 'Manufacturing'),
        ('CUSTOMER', 'Customer'),
        ('EMPLOYEE', 'Employee'),
    ]
    
    CALCULATION_METHODS = [
        ('SUM', 'Sum'),
        ('AVERAGE', 'Average'),
        ('COUNT', 'Count'),
        ('PERCENTAGE', 'Percentage'),
        ('RATIO', 'Ratio'),
        ('CUSTOM', 'Custom Formula'),
    ]
    
    FREQUENCY_CHOICES = [
        ('DAILY', 'Daily'),
        ('WEEKLY', 'Weekly'),
        ('MONTHLY', 'Monthly'),
        ('QUARTERLY', 'Quarterly'),
        ('YEARLY', 'Yearly'),
        ('REAL_TIME', 'Real Time'),
    ]

    category = models.ForeignKey(KPICategory, on_delete=models.CASCADE, related_name='kpis')
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField()
    kpi_type = models.CharField(max_length=20, choices=KPI_TYPES)
    calculation_method = models.CharField(max_length=20, choices=CALCULATION_METHODS)
    calculation_formula = models.TextField(help_text="SQL query or formula for calculation")
    unit = models.CharField(max_length=50, blank=True, help_text="e.g., IDR, %, units, days")
    target_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    warning_threshold = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    critical_threshold = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='MONTHLY')
    is_higher_better = models.BooleanField(default=True, help_text="True if higher values are better")
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'sort_order', 'name']

    def __str__(self):
        return f"{self.code} - {self.name}"


class KPIValue(models.Model):
    """Stores calculated KPI values over time"""
    kpi = models.ForeignKey(KPIDefinition, on_delete=models.CASCADE, related_name='values')
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    value = models.DecimalField(max_digits=15, decimal_places=2)
    target_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    variance = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    variance_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=[
        ('EXCELLENT', 'Excellent'),
        ('GOOD', 'Good'),
        ('WARNING', 'Warning'),
        ('CRITICAL', 'Critical'),
    ], default='GOOD')
    metadata = models.JSONField(default=dict, blank=True)
    calculated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['kpi', 'period_start', 'period_end']
        ordering = ['-period_start']

    def __str__(self):
        return f"{self.kpi.code} - {self.period_start.date()} to {self.period_end.date()}: {self.value}"

    def save(self, *args, **kwargs):
        # Calculate variance if target is set
        if self.target_value and self.target_value != 0:
            self.variance = self.value - self.target_value
            self.variance_percentage = (self.variance / self.target_value) * 100
        
        # Determine status based on thresholds
        if self.kpi.critical_threshold:
            if self.kpi.is_higher_better:
                if self.value < self.kpi.critical_threshold:
                    self.status = 'CRITICAL'
                elif self.kpi.warning_threshold and self.value < self.kpi.warning_threshold:
                    self.status = 'WARNING'
                elif self.target_value and self.value >= self.target_value * Decimal('1.1'):
                    self.status = 'EXCELLENT'
                else:
                    self.status = 'GOOD'
            else:
                if self.value > self.kpi.critical_threshold:
                    self.status = 'CRITICAL'
                elif self.kpi.warning_threshold and self.value > self.kpi.warning_threshold:
                    self.status = 'WARNING'
                elif self.target_value and self.value <= self.target_value * Decimal('0.9'):
                    self.status = 'EXCELLENT'
                else:
                    self.status = 'GOOD'
        
        super().save(*args, **kwargs)


class ReportTemplate(models.Model):
    """Templates for custom reports"""
    
    REPORT_TYPES = [
        ('TABULAR', 'Tabular Report'),
        ('CHART', 'Chart Report'),
        ('DASHBOARD', 'Dashboard'),
        ('FINANCIAL', 'Financial Statement'),
        ('OPERATIONAL', 'Operational Report'),
        ('COMPLIANCE', 'Compliance Report'),
    ]
    
    OUTPUT_FORMATS = [
        ('PDF', 'PDF'),
        ('EXCEL', 'Excel'),
        ('CSV', 'CSV'),
        ('HTML', 'HTML'),
        ('JSON', 'JSON'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField()
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES)
    category = models.CharField(max_length=100, blank=True)
    query = models.TextField(help_text="SQL query for data retrieval")
    parameters = models.JSONField(default=dict, help_text="Report parameters configuration")
    layout_config = models.JSONField(default=dict, help_text="Layout and formatting configuration")
    chart_config = models.JSONField(default=dict, blank=True, help_text="Chart configuration if applicable")
    output_formats = models.JSONField(default=list, help_text="Supported output formats")
    is_public = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return self.name


class ReportExecution(models.Model):
    """Tracks report executions and results"""
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('RUNNING', 'Running'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
    ]

    template = models.ForeignKey(ReportTemplate, on_delete=models.CASCADE, related_name='executions')
    executed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    parameters = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    output_format = models.CharField(max_length=10, default='PDF')
    file_path = models.CharField(max_length=500, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    execution_time = models.DurationField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.template.name} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class Dashboard(models.Model):
    """Custom dashboards for different user roles"""
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    layout_config = models.JSONField(default=dict, help_text="Dashboard layout configuration")
    widgets = models.JSONField(default=list, help_text="List of widgets and their configurations")
    filters = models.JSONField(default=dict, help_text="Default filters")
    refresh_interval = models.IntegerField(default=300, help_text="Auto-refresh interval in seconds")
    is_default = models.BooleanField(default=False)
    is_public = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class DataSource(models.Model):
    """External data sources for analytics"""
    
    SOURCE_TYPES = [
        ('DATABASE', 'Database'),
        ('API', 'API Endpoint'),
        ('FILE', 'File Upload'),
        ('WEBHOOK', 'Webhook'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPES)
    connection_config = models.JSONField(default=dict, help_text="Connection configuration")
    refresh_schedule = models.CharField(max_length=100, blank=True, help_text="Cron expression for refresh")
    last_refresh = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class AnalyticsCache(models.Model):
    """Cache for expensive analytics calculations"""
    cache_key = models.CharField(max_length=255, unique=True)
    data = models.JSONField()
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Cache: {self.cache_key}"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at


class BusinessMetric(models.Model):
    """Business metrics aggregation table"""
    
    METRIC_TYPES = [
        ('REVENUE', 'Revenue'),
        ('PROFIT', 'Profit'),
        ('COST', 'Cost'),
        ('VOLUME', 'Volume'),
        ('EFFICIENCY', 'Efficiency'),
        ('QUALITY', 'Quality'),
        ('CUSTOMER', 'Customer'),
        ('EMPLOYEE', 'Employee'),
    ]
    
    PERIODS = [
        ('DAILY', 'Daily'),
        ('WEEKLY', 'Weekly'),
        ('MONTHLY', 'Monthly'),
        ('QUARTERLY', 'Quarterly'),
        ('YEARLY', 'Yearly'),
    ]

    metric_name = models.CharField(max_length=200)
    metric_type = models.CharField(max_length=20, choices=METRIC_TYPES)
    period_type = models.CharField(max_length=20, choices=PERIODS)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    value = models.DecimalField(max_digits=15, decimal_places=2)
    unit = models.CharField(max_length=50, blank=True)
    dimensions = models.JSONField(default=dict, help_text="Additional dimensions like region, product, etc.")
    metadata = models.JSONField(default=dict)
    calculated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['metric_name', 'period_type', 'period_start', 'dimensions']
        ordering = ['-period_start']
        indexes = [
            models.Index(fields=['metric_name', 'period_type']),
            models.Index(fields=['period_start', 'period_end']),
            models.Index(fields=['metric_type']),
        ]

    def __str__(self):
        return f"{self.metric_name} - {self.period_start.date()}: {self.value} {self.unit}"


class AlertRule(models.Model):
    """Rules for automated alerts based on KPIs or metrics"""
    
    ALERT_TYPES = [
        ('THRESHOLD', 'Threshold Alert'),
        ('TREND', 'Trend Alert'),
        ('ANOMALY', 'Anomaly Alert'),
        ('COMPARISON', 'Comparison Alert'),
    ]
    
    NOTIFICATION_METHODS = [
        ('EMAIL', 'Email'),
        ('SMS', 'SMS'),
        ('WEBHOOK', 'Webhook'),
        ('IN_APP', 'In-App Notification'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField()
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    kpi = models.ForeignKey(KPIDefinition, on_delete=models.CASCADE, null=True, blank=True)
    condition = models.JSONField(help_text="Alert condition configuration")
    notification_methods = models.JSONField(default=list)
    recipients = models.JSONField(default=list, help_text="List of recipient emails or phone numbers")
    is_active = models.BooleanField(default=True)
    last_triggered = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class AlertInstance(models.Model):
    """Individual alert instances"""
    
    SEVERITY_LEVELS = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('CRITICAL', 'Critical'),
    ]
    
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('ACKNOWLEDGED', 'Acknowledged'),
        ('RESOLVED', 'Resolved'),
        ('DISMISSED', 'Dismissed'),
    ]

    rule = models.ForeignKey(AlertRule, on_delete=models.CASCADE, related_name='instances')
    severity = models.CharField(max_length=20, choices=SEVERITY_LEVELS)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    message = models.TextField()
    data = models.JSONField(default=dict, help_text="Alert data and context")
    acknowledged_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.rule.name} - {self.severity} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"
