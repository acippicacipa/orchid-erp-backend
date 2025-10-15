"""
Analytics Views for Orchid ERP Reporting & Business Intelligence
Provides comprehensive API endpoints for analytics, reporting, and business intelligence
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import connection
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from datetime import datetime, timedelta
import json
import csv
import io

from .models import (
    KPICategory, KPIDefinition, KPIValue, ReportTemplate, ReportExecution,
    Dashboard, DataSource, BusinessMetric, AlertRule, AlertInstance
)
from .serializers import (
    KPICategorySerializer, KPIDefinitionSerializer, KPIValueSerializer,
    ReportTemplateSerializer, ReportExecutionSerializer, DashboardSerializer,
    DataSourceSerializer, BusinessMetricSerializer, AlertRuleSerializer,
    AlertInstanceSerializer, SalesAnalyticsSerializer, PurchasingAnalyticsSerializer,
    InventoryAnalyticsSerializer, FinancialAnalyticsSerializer, DashboardDataSerializer,
    ReportBuilderTableSerializer, CustomReportSerializer
)
from .services import (
    AnalyticsService, KPICalculationService, ReportService, CacheService, AlertService
)


class KPICategoryViewSet(viewsets.ModelViewSet):
    """ViewSet for KPI categories"""
    queryset = KPICategory.objects.all()
    serializer_class = KPICategorySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.query_params.get('active_only') == 'true':
            queryset = queryset.filter(is_active=True)
        return queryset.order_by('sort_order', 'name')


class KPIDefinitionViewSet(viewsets.ModelViewSet):
    """ViewSet for KPI definitions"""
    queryset = KPIDefinition.objects.all()
    serializer_class = KPIDefinitionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by category
        category_id = self.request.query_params.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        
        # Filter by type
        kpi_type = self.request.query_params.get('type')
        if kpi_type:
            queryset = queryset.filter(kpi_type=kpi_type)
        
        # Filter by active status
        if self.request.query_params.get('active_only') == 'true':
            queryset = queryset.filter(is_active=True)
        
        return queryset.order_by('category__sort_order', 'sort_order', 'name')
    
    @action(detail=True, methods=['post'])
    def calculate(self, request, pk=None):
        """Calculate KPI value for a specific period"""
        kpi = self.get_object()
        
        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        
        if not start_date or not end_date:
            return Response(
                {'error': 'start_date and end_date are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            
            value = KPICalculationService.calculate_kpi(kpi, start_date, end_date)
            
            return Response({
                'kpi_code': kpi.code,
                'kpi_name': kpi.name,
                'period_start': start_date.isoformat(),
                'period_end': end_date.isoformat(),
                'value': value,
                'unit': kpi.unit,
                'formatted_value': f"{value} {kpi.unit}".strip(),
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def update_values(self, request, pk=None):
        """Update KPI values for all periods"""
        kpi = self.get_object()
        
        try:
            KPICalculationService.update_kpi(kpi)
            return Response({'message': f'KPI {kpi.code} values updated successfully'})
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class KPIValueViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for KPI values (read-only)"""
    queryset = KPIValue.objects.all()
    serializer_class = KPIValueSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by KPI
        kpi_id = self.request.query_params.get('kpi')
        if kpi_id:
            queryset = queryset.filter(kpi_id=kpi_id)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date:
            queryset = queryset.filter(period_start__gte=start_date)
        if end_date:
            queryset = queryset.filter(period_end__lte=end_date)
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.order_by('-period_start')


class ReportTemplateViewSet(viewsets.ModelViewSet):
    """ViewSet for report templates"""
    queryset = ReportTemplate.objects.all()
    serializer_class = ReportTemplateSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by type
        report_type = self.request.query_params.get('type')
        if report_type:
            queryset = queryset.filter(report_type=report_type)
        
        # Filter by category
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)
        
        # Filter by active status
        if self.request.query_params.get('active_only') == 'true':
            queryset = queryset.filter(is_active=True)
        
        # Filter by public/private
        if self.request.query_params.get('public_only') == 'true':
            queryset = queryset.filter(is_public=True)
        
        return queryset.order_by('category', 'name')
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        """Execute a report template"""
        template = self.get_object()
        parameters = request.data.get('parameters', {})
        
        try:
            execution = ReportService.execute_report(template, parameters, request.user)
            serializer = ReportExecutionSerializer(execution)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ReportExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for report executions (read-only)"""
    queryset = ReportExecution.objects.all()
    serializer_class = ReportExecutionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by template
        template_id = self.request.query_params.get('template')
        if template_id:
            queryset = queryset.filter(template_id=template_id)
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by user
        user_id = self.request.query_params.get('user')
        if user_id:
            queryset = queryset.filter(executed_by_id=user_id)
        
        return queryset.order_by('-created_at')
    
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Download report file"""
        execution = self.get_object()
        
        if execution.status != 'COMPLETED' or not execution.file_path:
            return Response(
                {'error': 'Report file not available'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            with open(execution.file_path, 'rb') as f:
                response = HttpResponse(f.read())
                
            # Set appropriate content type
            if execution.output_format == 'CSV':
                response['Content-Type'] = 'text/csv'
                response['Content-Disposition'] = f'attachment; filename="report_{execution.id}.csv"'
            elif execution.output_format == 'JSON':
                response['Content-Type'] = 'application/json'
                response['Content-Disposition'] = f'attachment; filename="report_{execution.id}.json"'
            else:
                response['Content-Type'] = 'application/octet-stream'
                response['Content-Disposition'] = f'attachment; filename="report_{execution.id}"'
            
            return response
            
        except FileNotFoundError:
            return Response(
                {'error': 'Report file not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class DashboardViewSet(viewsets.ModelViewSet):
    """ViewSet for dashboards"""
    queryset = Dashboard.objects.all()
    serializer_class = DashboardSerializer
    permission_classes = [IsAuthenticated]
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['get'])
    def data(self, request, pk=None):
        """Get dashboard data"""
        dashboard = self.get_object()
        
        # Get date range from request or use default (last 30 days)
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        if request.query_params.get('start_date'):
            start_date = datetime.fromisoformat(request.query_params['start_date'].replace('Z', '+00:00'))
        if request.query_params.get('end_date'):
            end_date = datetime.fromisoformat(request.query_params['end_date'].replace('Z', '+00:00'))
        
        # Check cache first
        cache_key = f"dashboard_{pk}_{start_date.date()}_{end_date.date()}"
        cached_data = CacheService.get_cached_data(cache_key)
        
        if cached_data:
            return Response(cached_data)
        
        # Calculate analytics data
        analytics_service = AnalyticsService()
        
        data = {
            'dashboard_id': dashboard.id,
            'dashboard_name': dashboard.name,
            'period_start': start_date.isoformat(),
            'period_end': end_date.isoformat(),
            'sales_analytics': analytics_service.calculate_sales_metrics(start_date, end_date),
            'purchasing_analytics': analytics_service.calculate_purchasing_metrics(start_date, end_date),
            'inventory_analytics': analytics_service.calculate_inventory_metrics(start_date, end_date),
            'financial_analytics': analytics_service.calculate_financial_metrics(start_date, end_date),
        }
        
        # Add KPI data
        active_kpis = KPIDefinition.objects.filter(is_active=True)[:10]
        kpi_data = []
        
        for kpi in active_kpis:
            latest_value = kpi.values.first()
            if latest_value:
                kpi_data.append({
                    'code': kpi.code,
                    'name': kpi.name,
                    'value': latest_value.value,
                    'unit': kpi.unit,
                    'status': latest_value.status,
                    'formatted_value': f"{latest_value.value} {kpi.unit}".strip(),
                })
        
        data['kpis'] = kpi_data
        
        # Add recent alerts
        recent_alerts = AlertInstance.objects.filter(
            status='ACTIVE',
            created_at__gte=start_date
        ).order_by('-created_at')[:5]
        
        data['recent_alerts'] = AlertInstanceSerializer(recent_alerts, many=True).data
        
        # Cache the data for 15 minutes
        CacheService.set_cached_data(cache_key, data, ttl_minutes=15)
        
        return Response(data)


class AnalyticsViewSet(viewsets.ViewSet):
    """ViewSet for analytics endpoints"""
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def overview(self, request):
        """Get analytics overview"""
        # Get date range
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        if request.query_params.get('start_date'):
            start_date = datetime.fromisoformat(request.query_params['start_date'].replace('Z', '+00:00'))
        if request.query_params.get('end_date'):
            end_date = datetime.fromisoformat(request.query_params['end_date'].replace('Z', '+00:00'))
        
        analytics_service = AnalyticsService()
        
        data = {
            'period_start': start_date.isoformat(),
            'period_end': end_date.isoformat(),
            'sales_analytics': analytics_service.calculate_sales_metrics(start_date, end_date),
            'purchasing_analytics': analytics_service.calculate_purchasing_metrics(start_date, end_date),
            'inventory_analytics': analytics_service.calculate_inventory_metrics(start_date, end_date),
            'financial_analytics': analytics_service.calculate_financial_metrics(start_date, end_date),
        }
        
        serializer = DashboardDataSerializer(data)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def sales(self, request):
        """Get sales analytics"""
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        if request.query_params.get('start_date'):
            start_date = datetime.fromisoformat(request.query_params['start_date'].replace('Z', '+00:00'))
        if request.query_params.get('end_date'):
            end_date = datetime.fromisoformat(request.query_params['end_date'].replace('Z', '+00:00'))
        
        analytics_service = AnalyticsService()
        data = analytics_service.calculate_sales_metrics(start_date, end_date)
        
        serializer = SalesAnalyticsSerializer(data)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def purchasing(self, request):
        """Get purchasing analytics"""
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        if request.query_params.get('start_date'):
            start_date = datetime.fromisoformat(request.query_params['start_date'].replace('Z', '+00:00'))
        if request.query_params.get('end_date'):
            end_date = datetime.fromisoformat(request.query_params['end_date'].replace('Z', '+00:00'))
        
        analytics_service = AnalyticsService()
        data = analytics_service.calculate_purchasing_metrics(start_date, end_date)
        
        serializer = PurchasingAnalyticsSerializer(data)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def inventory(self, request):
        """Get inventory analytics"""
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        if request.query_params.get('start_date'):
            start_date = datetime.fromisoformat(request.query_params['start_date'].replace('Z', '+00:00'))
        if request.query_params.get('end_date'):
            end_date = datetime.fromisoformat(request.query_params['end_date'].replace('Z', '+00:00'))
        
        analytics_service = AnalyticsService()
        data = analytics_service.calculate_inventory_metrics(start_date, end_date)
        
        serializer = InventoryAnalyticsSerializer(data)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def financial(self, request):
        """Get financial analytics"""
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        if request.query_params.get('start_date'):
            start_date = datetime.fromisoformat(request.query_params['start_date'].replace('Z', '+00:00'))
        if request.query_params.get('end_date'):
            end_date = datetime.fromisoformat(request.query_params['end_date'].replace('Z', '+00:00'))
        
        analytics_service = AnalyticsService()
        data = analytics_service.calculate_financial_metrics(start_date, end_date)
        
        serializer = FinancialAnalyticsSerializer(data)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def update_kpis(self, request):
        """Update all KPI values"""
        try:
            KPICalculationService.update_all_kpis()
            return Response({'message': 'All KPIs updated successfully'})
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ReportBuilderViewSet(viewsets.ViewSet):
    """ViewSet for report builder functionality"""
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def tables(self, request):
        """Get available tables for report building"""
        tables = [
            {
                'name': 'sales_salesorder',
                'label': 'Sales Orders',
                'description': 'Sales order data',
                'fields': [
                    {'name': 'order_number', 'label': 'Order Number', 'type': 'string', 'table': 'sales_salesorder'},
                    {'name': 'order_date', 'label': 'Order Date', 'type': 'date', 'table': 'sales_salesorder'},
                    {'name': 'total_amount', 'label': 'Total Amount', 'type': 'decimal', 'table': 'sales_salesorder', 'aggregatable': True},
                    {'name': 'status', 'label': 'Status', 'type': 'string', 'table': 'sales_salesorder'},
                ]
            },
            {
                'name': 'purchasing_purchaseorder',
                'label': 'Purchase Orders',
                'description': 'Purchase order data',
                'fields': [
                    {'name': 'order_number', 'label': 'Order Number', 'type': 'string', 'table': 'purchasing_purchaseorder'},
                    {'name': 'order_date', 'label': 'Order Date', 'type': 'date', 'table': 'purchasing_purchaseorder'},
                    {'name': 'total_amount', 'label': 'Total Amount', 'type': 'decimal', 'table': 'purchasing_purchaseorder', 'aggregatable': True},
                    {'name': 'status', 'label': 'Status', 'type': 'string', 'table': 'purchasing_purchaseorder'},
                ]
            },
            {
                'name': 'inventory_product',
                'label': 'Products',
                'description': 'Product inventory data',
                'fields': [
                    {'name': 'name', 'label': 'Product Name', 'type': 'string', 'table': 'inventory_product'},
                    {'name': 'sku', 'label': 'SKU', 'type': 'string', 'table': 'inventory_product'},
                    {'name': 'current_stock', 'label': 'Current Stock', 'type': 'number', 'table': 'inventory_product', 'aggregatable': True},
                    {'name': 'cost_price', 'label': 'Cost Price', 'type': 'decimal', 'table': 'inventory_product', 'aggregatable': True},
                ]
            },
            {
                'name': 'accounting_journalentry',
                'label': 'Journal Entries',
                'description': 'Accounting journal entries',
                'fields': [
                    {'name': 'entry_number', 'label': 'Entry Number', 'type': 'string', 'table': 'accounting_journalentry'},
                    {'name': 'entry_date', 'label': 'Entry Date', 'type': 'date', 'table': 'accounting_journalentry'},
                    {'name': 'total_debit', 'label': 'Total Debit', 'type': 'decimal', 'table': 'accounting_journalentry', 'aggregatable': True},
                    {'name': 'total_credit', 'label': 'Total Credit', 'type': 'decimal', 'table': 'accounting_journalentry', 'aggregatable': True},
                ]
            }
        ]
        
        serializer = ReportBuilderTableSerializer(tables, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def build(self, request):
        """Build and execute a custom report"""
        serializer = CustomReportSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        
        try:
            # Build SQL query
            query = self._build_query(data)
            
            # Execute query
            with connection.cursor() as cursor:
                cursor.execute(query)
                columns = [col[0] for col in cursor.description]
                results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            # Return results based on output format
            output_format = data.get('output_format', 'JSON')
            
            if output_format == 'CSV':
                return self._export_csv(results, data['name'])
            else:
                return Response({
                    'name': data['name'],
                    'description': data.get('description', ''),
                    'query': query,
                    'results': results,
                    'count': len(results),
                })
                
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _build_query(self, data):
        """Build SQL query from report specification"""
        tables = data['tables']
        fields = data['fields']
        filters = data.get('filters', {})
        grouping = data.get('grouping', [])
        sorting = data.get('sorting', [])
        
        # Build SELECT clause
        select_fields = []
        for field in fields:
            if '.' in field:
                select_fields.append(field)
            else:
                # Assume first table if no table specified
                select_fields.append(f"{tables[0]}.{field}")
        
        query = f"SELECT {', '.join(select_fields)}"
        
        # Build FROM clause
        query += f" FROM {tables[0]}"
        
        # Add JOINs for additional tables (simplified)
        for table in tables[1:]:
            query += f" LEFT JOIN {table} ON {tables[0]}.id = {table}.id"
        
        # Build WHERE clause
        where_conditions = []
        for field, condition in filters.items():
            if isinstance(condition, dict):
                operator = condition.get('operator', 'eq')
                value = condition.get('value')
                
                if operator == 'eq':
                    where_conditions.append(f"{field} = '{value}'")
                elif operator == 'gt':
                    where_conditions.append(f"{field} > '{value}'")
                elif operator == 'lt':
                    where_conditions.append(f"{field} < '{value}'")
                elif operator == 'contains':
                    where_conditions.append(f"{field} LIKE '%{value}%'")
        
        if where_conditions:
            query += f" WHERE {' AND '.join(where_conditions)}"
        
        # Build GROUP BY clause
        if grouping:
            query += f" GROUP BY {', '.join(grouping)}"
        
        # Build ORDER BY clause
        if sorting:
            order_clauses = []
            for sort in sorting:
                field = sort.get('field')
                direction = sort.get('direction', 'ASC')
                order_clauses.append(f"{field} {direction}")
            query += f" ORDER BY {', '.join(order_clauses)}"
        
        return query
    
    def _export_csv(self, results, filename):
        """Export results as CSV"""
        output = io.StringIO()
        
        if results:
            writer = csv.DictWriter(output, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        
        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
        
        return response


class AlertRuleViewSet(viewsets.ModelViewSet):
    """ViewSet for alert rules"""
    queryset = AlertRule.objects.all()
    serializer_class = AlertRuleSerializer
    permission_classes = [IsAuthenticated]
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=False, methods=['post'])
    def check_all(self, request):
        """Check all alert rules"""
        try:
            AlertService.check_all_alerts()
            return Response({'message': 'All alert rules checked successfully'})
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AlertInstanceViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for alert instances (read-only)"""
    queryset = AlertInstance.objects.all()
    serializer_class = AlertInstanceSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by severity
        severity = self.request.query_params.get('severity')
        if severity:
            queryset = queryset.filter(severity=severity)
        
        # Filter by rule
        rule_id = self.request.query_params.get('rule')
        if rule_id:
            queryset = queryset.filter(rule_id=rule_id)
        
        return queryset.order_by('-created_at')
    
    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        """Acknowledge an alert"""
        alert = self.get_object()
        alert.status = 'ACKNOWLEDGED'
        alert.acknowledged_by = request.user
        alert.acknowledged_at = timezone.now()
        alert.save()
        
        serializer = self.get_serializer(alert)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Resolve an alert"""
        alert = self.get_object()
        alert.status = 'RESOLVED'
        alert.resolved_at = timezone.now()
        alert.save()
        
        serializer = self.get_serializer(alert)
        return Response(serializer.data)
