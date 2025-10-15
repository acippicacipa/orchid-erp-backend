"""
Analytics Services for Orchid ERP
Provides data aggregation, KPI calculation, and business intelligence services
"""

from django.db import connection, transaction
from django.db.models import Sum, Avg, Count, Q, F
from django.utils import timezone
from datetime import datetime, timedelta, date
from decimal import Decimal
import json
import logging
from typing import Dict, List, Any, Optional

from .models import (
    KPIDefinition, KPIValue, BusinessMetric, AnalyticsCache,
    ReportTemplate, ReportExecution, AlertRule, AlertInstance
)
from sales.models import SalesOrder, Customer, Invoice, Payment as SalesPayment
from purchasing.models import PurchaseOrder, Supplier, Bill, SupplierPayment
from inventory.models import Product, StockMovement, Location
from accounting.models import Account, JournalEntry, JournalEntryLine

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Core analytics service for data aggregation and calculations"""
    
    @staticmethod
    def get_date_range(period_type: str, periods_back: int = 0) -> tuple:
        """Get date range for a given period type"""
        now = timezone.now()
        
        if period_type == 'DAILY':
            start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=periods_back)
            end = start + timedelta(days=1) - timedelta(microseconds=1)
        elif period_type == 'WEEKLY':
            days_since_monday = now.weekday()
            start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
                days=days_since_monday + (periods_back * 7)
            )
            end = start + timedelta(days=7) - timedelta(microseconds=1)
        elif period_type == 'MONTHLY':
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if periods_back > 0:
                for _ in range(periods_back):
                    start = start.replace(day=1) - timedelta(days=1)
                    start = start.replace(day=1)
            # Get last day of month
            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1, day=1) - timedelta(microseconds=1)
            else:
                end = start.replace(month=start.month + 1, day=1) - timedelta(microseconds=1)
        elif period_type == 'QUARTERLY':
            quarter = ((now.month - 1) // 3) + 1 - periods_back
            year = now.year
            while quarter <= 0:
                quarter += 4
                year -= 1
            start = datetime(year, (quarter - 1) * 3 + 1, 1)
            start = timezone.make_aware(start)
            end_month = quarter * 3
            if end_month == 12:
                end = datetime(year + 1, 1, 1) - timedelta(microseconds=1)
            else:
                end = datetime(year, end_month + 1, 1) - timedelta(microseconds=1)
            end = timezone.make_aware(end)
        elif period_type == 'YEARLY':
            start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            start = start.replace(year=start.year - periods_back)
            end = start.replace(year=start.year + 1) - timedelta(microseconds=1)
        else:
            raise ValueError(f"Invalid period type: {period_type}")
        
        return start, end

    @staticmethod
    def calculate_sales_metrics(start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Calculate sales-related metrics"""
        sales_orders = SalesOrder.objects.filter(
            order_date__range=[start_date, end_date],
            status__in=['CONFIRMED', 'DELIVERED', 'COMPLETED']
        )
        
        invoices = Invoice.objects.filter(
            invoice_date__range=[start_date, end_date]
        )
        
        payments = SalesPayment.objects.filter(
            payment_date__range=[start_date, end_date]
        )
        
        return {
            'total_sales_orders': sales_orders.count(),
            'total_sales_value': sales_orders.aggregate(total=Sum('total_amount'))['total'] or Decimal('0'),
            'average_order_value': sales_orders.aggregate(avg=Avg('total_amount'))['avg'] or Decimal('0'),
            'total_invoices': invoices.count(),
            'total_invoice_value': invoices.aggregate(total=Sum('total_amount'))['total'] or Decimal('0'),
            'total_payments': payments.count(),
            'total_payment_value': payments.aggregate(total=Sum('amount'))['total'] or Decimal('0'),
            'unique_customers': sales_orders.values('customer').distinct().count(),
            'new_customers': Customer.objects.filter(created_at__range=[start_date, end_date]).count(),
        }

    @staticmethod
    def calculate_purchasing_metrics(start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Calculate purchasing-related metrics"""
        purchase_orders = PurchaseOrder.objects.filter(
            order_date__range=[start_date, end_date],
            status__in=['CONFIRMED', 'RECEIVED', 'COMPLETED']
        )
        
        bills = Bill.objects.filter(
            bill_date__range=[start_date, end_date]
        )
        
        payments = SupplierPayment.objects.filter(
            payment_date__range=[start_date, end_date]
        )
        
        return {
            'total_purchase_orders': purchase_orders.count(),
            'total_purchase_value': purchase_orders.aggregate(total=Sum('total_amount'))['total'] or Decimal('0'),
            'average_purchase_value': purchase_orders.aggregate(avg=Avg('total_amount'))['avg'] or Decimal('0'),
            'total_bills': bills.count(),
            'total_bill_value': bills.aggregate(total=Sum('total_amount'))['total'] or Decimal('0'),
            'total_supplier_payments': payments.count(),
            'total_payment_value': payments.aggregate(total=Sum('amount'))['total'] or Decimal('0'),
            'unique_suppliers': purchase_orders.values('supplier').distinct().count(),
            'new_suppliers': Supplier.objects.filter(created_at__range=[start_date, end_date]).count(),
        }

    @staticmethod
    def calculate_inventory_metrics(start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Calculate inventory-related metrics"""
        stock_movements = StockMovement.objects.filter(
            movement_date__range=[start_date, end_date]
        )
        
        # Current inventory value
        products = Product.objects.filter(is_active=True)
        total_inventory_value = sum(
            (product.current_stock or 0) * (product.cost_price or 0) 
            for product in products
        )
        
        # Stock movements by type
        movements_in = stock_movements.filter(
            movement_type__in=['PURCHASE', 'ADJUSTMENT', 'RETURN', 'PRODUCTION']
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        movements_out = stock_movements.filter(
            movement_type__in=['SALE', 'ADJUSTMENT', 'TRANSFER', 'CONSUMPTION']
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        return {
            'total_products': products.count(),
            'total_inventory_value': Decimal(str(total_inventory_value)),
            'stock_movements_count': stock_movements.count(),
            'stock_movements_in': movements_in,
            'stock_movements_out': abs(movements_out),
            'net_stock_change': movements_in + movements_out,  # movements_out is negative
            'low_stock_products': products.filter(
                current_stock__lte=F('minimum_stock_level')
            ).count(),
            'out_of_stock_products': products.filter(current_stock__lte=0).count(),
        }

    @staticmethod
    def calculate_financial_metrics(start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Calculate financial metrics from accounting data"""
        journal_entries = JournalEntry.objects.filter(
            entry_date__range=[start_date, end_date],
            status='POSTED'
        )
        
        # Get account balances
        asset_accounts = Account.objects.filter(account_type__category='ASSET', is_active=True)
        liability_accounts = Account.objects.filter(account_type__category='LIABILITY', is_active=True)
        equity_accounts = Account.objects.filter(account_type__category='EQUITY', is_active=True)
        revenue_accounts = Account.objects.filter(account_type__category='REVENUE', is_active=True)
        expense_accounts = Account.objects.filter(account_type__category='EXPENSE', is_active=True)
        
        total_assets = sum(acc.current_balance or 0 for acc in asset_accounts)
        total_liabilities = sum(acc.current_balance or 0 for acc in liability_accounts)
        total_equity = sum(acc.current_balance or 0 for acc in equity_accounts)
        
        # Revenue and expenses for the period
        revenue_lines = JournalEntryLine.objects.filter(
            journal_entry__in=journal_entries,
            account__in=revenue_accounts
        )
        expense_lines = JournalEntryLine.objects.filter(
            journal_entry__in=journal_entries,
            account__in=expense_accounts
        )
        
        total_revenue = revenue_lines.aggregate(total=Sum('credit_amount'))['total'] or Decimal('0')
        total_expenses = expense_lines.aggregate(total=Sum('debit_amount'))['total'] or Decimal('0')
        net_income = total_revenue - total_expenses
        
        # Cash accounts
        cash_accounts = Account.objects.filter(
            Q(cash_account=True) | Q(bank_account=True),
            is_active=True
        )
        total_cash = sum(acc.current_balance or 0 for acc in cash_accounts)
        
        return {
            'total_assets': Decimal(str(total_assets)),
            'total_liabilities': Decimal(str(total_liabilities)),
            'total_equity': Decimal(str(total_equity)),
            'total_revenue': total_revenue,
            'total_expenses': total_expenses,
            'net_income': net_income,
            'total_cash': Decimal(str(total_cash)),
            'journal_entries_count': journal_entries.count(),
            'profit_margin': (net_income / total_revenue * 100) if total_revenue > 0 else Decimal('0'),
            'return_on_assets': (net_income / Decimal(str(total_assets)) * 100) if total_assets > 0 else Decimal('0'),
        }


class KPICalculationService:
    """Service for calculating and updating KPI values"""
    
    @staticmethod
    def calculate_kpi(kpi: KPIDefinition, start_date: datetime, end_date: datetime) -> Decimal:
        """Calculate KPI value for a given period"""
        try:
            if kpi.calculation_method == 'CUSTOM':
                # Execute custom SQL query
                with connection.cursor() as cursor:
                    query = kpi.calculation_formula.format(
                        start_date=start_date.strftime('%Y-%m-%d'),
                        end_date=end_date.strftime('%Y-%m-%d')
                    )
                    cursor.execute(query)
                    result = cursor.fetchone()
                    return Decimal(str(result[0])) if result and result[0] is not None else Decimal('0')
            
            # Built-in calculation methods
            analytics = AnalyticsService()
            
            if kpi.kpi_type == 'SALES':
                metrics = analytics.calculate_sales_metrics(start_date, end_date)
                return KPICalculationService._extract_metric_value(kpi.code, metrics)
            
            elif kpi.kpi_type == 'PURCHASING':
                metrics = analytics.calculate_purchasing_metrics(start_date, end_date)
                return KPICalculationService._extract_metric_value(kpi.code, metrics)
            
            elif kpi.kpi_type == 'INVENTORY':
                metrics = analytics.calculate_inventory_metrics(start_date, end_date)
                return KPICalculationService._extract_metric_value(kpi.code, metrics)
            
            elif kpi.kpi_type == 'FINANCIAL':
                metrics = analytics.calculate_financial_metrics(start_date, end_date)
                return KPICalculationService._extract_metric_value(kpi.code, metrics)
            
            else:
                logger.warning(f"Unknown KPI type: {kpi.kpi_type}")
                return Decimal('0')
                
        except Exception as e:
            logger.error(f"Error calculating KPI {kpi.code}: {str(e)}")
            return Decimal('0')

    @staticmethod
    def _extract_metric_value(kpi_code: str, metrics: Dict[str, Any]) -> Decimal:
        """Extract specific metric value based on KPI code"""
        metric_mapping = {
            # Sales KPIs
            'SALES_REVENUE': 'total_sales_value',
            'SALES_ORDERS_COUNT': 'total_sales_orders',
            'AVERAGE_ORDER_VALUE': 'average_order_value',
            'NEW_CUSTOMERS': 'new_customers',
            'CUSTOMER_COUNT': 'unique_customers',
            
            # Purchasing KPIs
            'PURCHASE_SPEND': 'total_purchase_value',
            'PURCHASE_ORDERS_COUNT': 'total_purchase_orders',
            'SUPPLIER_COUNT': 'unique_suppliers',
            
            # Inventory KPIs
            'INVENTORY_VALUE': 'total_inventory_value',
            'STOCK_TURNOVER': 'net_stock_change',
            'LOW_STOCK_COUNT': 'low_stock_products',
            'OUT_OF_STOCK_COUNT': 'out_of_stock_products',
            
            # Financial KPIs
            'NET_INCOME': 'net_income',
            'TOTAL_REVENUE': 'total_revenue',
            'TOTAL_EXPENSES': 'total_expenses',
            'PROFIT_MARGIN': 'profit_margin',
            'TOTAL_ASSETS': 'total_assets',
            'CASH_BALANCE': 'total_cash',
        }
        
        metric_key = metric_mapping.get(kpi_code)
        if metric_key and metric_key in metrics:
            value = metrics[metric_key]
            return Decimal(str(value)) if value is not None else Decimal('0')
        
        logger.warning(f"No metric mapping found for KPI code: {kpi_code}")
        return Decimal('0')

    @staticmethod
    def update_all_kpis():
        """Update all active KPIs"""
        active_kpis = KPIDefinition.objects.filter(is_active=True)
        
        for kpi in active_kpis:
            try:
                KPICalculationService.update_kpi(kpi)
            except Exception as e:
                logger.error(f"Error updating KPI {kpi.code}: {str(e)}")

    @staticmethod
    def update_kpi(kpi: KPIDefinition):
        """Update a specific KPI"""
        analytics = AnalyticsService()
        
        # Determine how many periods to calculate based on frequency
        periods_to_calculate = {
            'DAILY': 30,    # Last 30 days
            'WEEKLY': 12,   # Last 12 weeks
            'MONTHLY': 12,  # Last 12 months
            'QUARTERLY': 8, # Last 8 quarters
            'YEARLY': 5,    # Last 5 years
        }.get(kpi.frequency, 12)
        
        for period_back in range(periods_to_calculate):
            start_date, end_date = analytics.get_date_range(kpi.frequency, period_back)
            
            # Check if value already exists
            existing_value = KPIValue.objects.filter(
                kpi=kpi,
                period_start=start_date,
                period_end=end_date
            ).first()
            
            if existing_value:
                continue  # Skip if already calculated
            
            # Calculate new value
            value = KPICalculationService.calculate_kpi(kpi, start_date, end_date)
            
            # Create KPI value record
            KPIValue.objects.create(
                kpi=kpi,
                period_start=start_date,
                period_end=end_date,
                value=value,
                target_value=kpi.target_value
            )


class ReportService:
    """Service for report generation and management"""
    
    @staticmethod
    def execute_report(template: ReportTemplate, parameters: Dict[str, Any], user) -> ReportExecution:
        """Execute a report template"""
        execution = ReportExecution.objects.create(
            template=template,
            executed_by=user,
            parameters=parameters,
            status='PENDING'
        )
        
        try:
            execution.status = 'RUNNING'
            execution.started_at = timezone.now()
            execution.save()
            
            # Execute the report query
            data = ReportService._execute_query(template.query, parameters)
            
            # Generate output based on format
            output_format = parameters.get('output_format', 'JSON')
            file_path = ReportService._generate_output(data, template, output_format, execution.id)
            
            execution.status = 'COMPLETED'
            execution.completed_at = timezone.now()
            execution.file_path = file_path
            execution.execution_time = execution.completed_at - execution.started_at
            execution.save()
            
        except Exception as e:
            execution.status = 'FAILED'
            execution.error_message = str(e)
            execution.completed_at = timezone.now()
            execution.save()
            logger.error(f"Report execution failed: {str(e)}")
        
        return execution

    @staticmethod
    def _execute_query(query: str, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Execute SQL query with parameters"""
        with connection.cursor() as cursor:
            cursor.execute(query, parameters)
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    @staticmethod
    def _generate_output(data: List[Dict[str, Any]], template: ReportTemplate, 
                        output_format: str, execution_id: int) -> str:
        """Generate report output in specified format"""
        import os
        import csv
        from django.conf import settings
        
        # Create reports directory if it doesn't exist
        reports_dir = os.path.join(settings.MEDIA_ROOT, 'reports')
        os.makedirs(reports_dir, exist_ok=True)
        
        filename = f"report_{execution_id}_{timezone.now().strftime('%Y%m%d_%H%M%S')}"
        
        if output_format == 'CSV':
            file_path = os.path.join(reports_dir, f"{filename}.csv")
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                if data:
                    writer = csv.DictWriter(csvfile, fieldnames=data[0].keys())
                    writer.writeheader()
                    writer.writerows(data)
        
        elif output_format == 'JSON':
            file_path = os.path.join(reports_dir, f"{filename}.json")
            with open(file_path, 'w', encoding='utf-8') as jsonfile:
                json.dump(data, jsonfile, indent=2, default=str)
        
        else:
            # Default to JSON
            file_path = os.path.join(reports_dir, f"{filename}.json")
            with open(file_path, 'w', encoding='utf-8') as jsonfile:
                json.dump(data, jsonfile, indent=2, default=str)
        
        return file_path


class CacheService:
    """Service for analytics caching"""
    
    @staticmethod
    def get_cached_data(cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached analytics data"""
        try:
            cache_entry = AnalyticsCache.objects.get(cache_key=cache_key)
            if not cache_entry.is_expired:
                return cache_entry.data
            else:
                cache_entry.delete()
                return None
        except AnalyticsCache.DoesNotExist:
            return None

    @staticmethod
    def set_cached_data(cache_key: str, data: Dict[str, Any], ttl_minutes: int = 60):
        """Cache analytics data"""
        expires_at = timezone.now() + timedelta(minutes=ttl_minutes)
        
        AnalyticsCache.objects.update_or_create(
            cache_key=cache_key,
            defaults={
                'data': data,
                'expires_at': expires_at
            }
        )

    @staticmethod
    def clear_expired_cache():
        """Clear expired cache entries"""
        AnalyticsCache.objects.filter(expires_at__lt=timezone.now()).delete()


class AlertService:
    """Service for managing alerts and notifications"""
    
    @staticmethod
    def check_all_alerts():
        """Check all active alert rules"""
        active_rules = AlertRule.objects.filter(is_active=True)
        
        for rule in active_rules:
            try:
                AlertService.check_alert_rule(rule)
            except Exception as e:
                logger.error(f"Error checking alert rule {rule.name}: {str(e)}")

    @staticmethod
    def check_alert_rule(rule: AlertRule):
        """Check a specific alert rule"""
        if rule.alert_type == 'THRESHOLD' and rule.kpi:
            # Get latest KPI value
            latest_value = KPIValue.objects.filter(kpi=rule.kpi).first()
            
            if latest_value:
                condition = rule.condition
                threshold = Decimal(str(condition.get('threshold', 0)))
                operator = condition.get('operator', 'gt')  # gt, lt, eq, gte, lte
                
                triggered = False
                if operator == 'gt' and latest_value.value > threshold:
                    triggered = True
                elif operator == 'lt' and latest_value.value < threshold:
                    triggered = True
                elif operator == 'gte' and latest_value.value >= threshold:
                    triggered = True
                elif operator == 'lte' and latest_value.value <= threshold:
                    triggered = True
                elif operator == 'eq' and latest_value.value == threshold:
                    triggered = True
                
                if triggered:
                    AlertService.create_alert_instance(rule, latest_value)

    @staticmethod
    def create_alert_instance(rule: AlertRule, kpi_value: KPIValue):
        """Create an alert instance"""
        # Check if similar alert already exists and is active
        existing_alert = AlertInstance.objects.filter(
            rule=rule,
            status='ACTIVE',
            created_at__gte=timezone.now() - timedelta(hours=1)  # Don't spam alerts
        ).first()
        
        if existing_alert:
            return existing_alert
        
        # Determine severity based on how far from threshold
        condition = rule.condition
        threshold = Decimal(str(condition.get('threshold', 0)))
        variance = abs(kpi_value.value - threshold)
        
        if variance > threshold * Decimal('0.5'):
            severity = 'CRITICAL'
        elif variance > threshold * Decimal('0.25'):
            severity = 'HIGH'
        elif variance > threshold * Decimal('0.1'):
            severity = 'MEDIUM'
        else:
            severity = 'LOW'
        
        message = f"KPI {rule.kpi.name} is {kpi_value.value} {rule.kpi.unit}, " \
                 f"which is beyond the threshold of {threshold} {rule.kpi.unit}"
        
        alert_instance = AlertInstance.objects.create(
            rule=rule,
            severity=severity,
            message=message,
            data={
                'kpi_code': rule.kpi.code,
                'kpi_value': str(kpi_value.value),
                'threshold': str(threshold),
                'variance': str(variance),
                'period_start': kpi_value.period_start.isoformat(),
                'period_end': kpi_value.period_end.isoformat(),
            }
        )
        
        # Update rule's last triggered time
        rule.last_triggered = timezone.now()
        rule.save()
        
        return alert_instance
