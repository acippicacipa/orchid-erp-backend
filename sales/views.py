from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Sum, Count
from django.utils import timezone
from datetime import datetime, timedelta
from accounts.permissions import IsAdminOrSales
from rest_framework.permissions import AllowAny
from .services import PricingService
from .models import Customer, CustomerGroup, Product, SalesOrder, SalesOrderItem, Invoice, Payment, DownPayment, DownPaymentUsage
from .serializers import (
    CustomerSerializer, CustomerListSerializer, CustomerGroupSerializer,
    SalesOrderSerializer, SalesOrderListSerializer, SalesOrderItemSerializer,
    InvoiceSerializer, InvoiceListSerializer, PaymentSerializer,
    ProductSearchSerializer, DownPaymentSerializer, DownPaymentUsageSerializer,
    CustomerDownPaymentSummarySerializer
)
from inventory.models import Product
from decimal import Decimal, InvalidOperation

class CustomerGroupViewSet(viewsets.ModelViewSet):
    """
    ViewSet untuk mengelola grup customer.
    """
    queryset = CustomerGroup.objects.all()
    serializer_class = CustomerGroupSerializer
    permission_classes = [IsAdminOrSales]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name']
    ordering = ['name']

class CustomerViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing customers with search and filtering
    """
    queryset = Customer.objects.select_related('customer_group').all()
    permission_classes = [IsAdminOrSales]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'city', 'state', 'country']
    search_fields = ['name', 'customer_id', 'email', 'phone', 'company_name', 'contact_person']
    ordering_fields = ['name', 'customer_id', 'created_at', 'city']
    ordering = ['name']

    def get_serializer_class(self):
        if self.action == 'list':
            return CustomerListSerializer
        return CustomerSerializer

    @action(detail=False, methods=['get'])
    def search(self, request):
        """Search customers for dropdown selection"""
        query = request.query_params.get('q', '')
        if len(query) < 2:
            return Response([])
        
        customers = Customer.objects.filter(
            Q(name__icontains=query) |
            Q(customer_id__icontains=query) |
            Q(email__icontains=query) |
            Q(company_name__icontains=query),
            is_active=True
        ).order_by('name')[:10]
        
        serializer = CustomerListSerializer(customers, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def sales_summary(self, request, pk=None):
        """Get customer sales summary"""
        customer = self.get_object()
        
        # Get sales statistics
        sales_orders = SalesOrder.objects.filter(customer=customer)
        invoices = Invoice.objects.filter(customer=customer)
        
        summary = {
            'total_orders': sales_orders.count(),
            'total_sales_amount': sales_orders.aggregate(total=Sum('total_amount'))['total'] or 0,
            'total_invoices': invoices.count(),
            'total_invoice_amount': invoices.aggregate(total=Sum('total_amount'))['total'] or 0,
            'outstanding_balance': invoices.aggregate(total=Sum('balance_due'))['total'] or 0,
            'last_order_date': sales_orders.order_by('-order_date').first().order_date if sales_orders.exists() else None,
        }
        
        return Response(summary)

class ProductSearchViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for product search in sales orders
    """
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSearchSerializer
    permission_classes = [IsAdminOrSales]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'sku', 'description']
    ordering_fields = ['name', 'sku', 'price']
    ordering = ['name']

    @action(detail=False, methods=['get'])
    def search(self, request):
        """Search products for sales order dropdown"""
        query = request.query_params.get('q', '')
        if len(query) < 2:
            return Response([])
        
        products = Product.objects.filter(
            Q(name__icontains=query) |
            Q(sku__icontains=query) |
            Q(description__icontains=query),
            is_active=True,
            is_sellable=True # Pastikan hanya produk yang bisa dijual yang muncul
        ).select_related('main_category', 'sub_category').order_by('name')[:20]
        
        serializer = ProductSearchSerializer(products, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], url_path='calculate-price')
    def calculate_price(self, request, pk=None):
        """
        Calculates the price and discount for a product based on customer and quantity.
        Expects 'customer_id' and 'quantity' as query parameters.
        """
        product = self.get_object()
        
        customer_id = request.query_params.get('customer_id')
        quantity_str = request.query_params.get('quantity', '1')

        if not customer_id:
            return Response(
                {'error': 'customer_id is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            customer = Customer.objects.get(pk=customer_id)
        except Customer.DoesNotExist:
            return Response({'error': f"Customer with ID {customer_id} not found"}, status=status.HTTP_404_NOT_FOUND)
        except (ValueError, TypeError):
             return Response({'error': 'Invalid customer_id format'}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Validasi Kuantitas secara terpisah
        try:
            quantity = Decimal(quantity_str)
            if quantity <= 0:
                raise InvalidOperation("Quantity must be positive.")
        except InvalidOperation as e: # Tangkap error konversi Decimal secara spesifik
            return Response({'error': f"Invalid quantity: {e}"}, status=status.HTTP_400_BAD_REQUEST)
            
        # Jika semua validasi lolos, panggil service
        pricing_data = PricingService.get_price_and_discount(customer, product, quantity)
        
        return Response(pricing_data)

class SalesOrderViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing sales orders with advanced features
    """
    queryset = SalesOrder.objects.all().select_related('customer').prefetch_related('items__product')
    permission_classes = [IsAdminOrSales]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'customer', 'order_date']
    search_fields = ['order_number', 'customer__name', 'notes']
    ordering_fields = ['order_date', 'order_number', 'total_amount', 'created_at']
    ordering = ['-order_date', '-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return SalesOrderListSerializer
        return SalesOrderSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """Confirm a sales order"""
        sales_order = self.get_object()
        
        if sales_order.status != 'DRAFT':
            return Response(
                {'error': 'Only draft orders can be confirmed'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check inventory availability
        insufficient_stock = []
        for item in sales_order.items.all():
            if item.product.stock_quantity < item.quantity:
                insufficient_stock.append({
                    'product': item.product.name,
                    'required': float(item.quantity),
                    'available': float(item.product.stock_quantity)
                })
        
        if insufficient_stock:
            return Response(
                {'error': 'Insufficient stock', 'details': insufficient_stock},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        sales_order.status = 'CONFIRMED'
        sales_order.save()
        
        return Response({'message': 'Sales order confirmed successfully'})

    @action(detail=True, methods=['post'])
    def ship(self, request, pk=None):
        """Mark sales order as shipped and update inventory"""
        sales_order = self.get_object()
        
        if sales_order.status != 'CONFIRMED':
            return Response(
                {'error': 'Only confirmed orders can be shipped'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update inventory
        for item in sales_order.items.all():
            product = item.product
            if product.stock_quantity < item.quantity:
                return Response(
                    {'error': f'Insufficient stock for {product.name}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            product.stock_quantity -= item.quantity
            product.save()
        
        sales_order.status = 'SHIPPED'
        sales_order.save()
        
        return Response({'message': 'Sales order shipped and inventory updated'})

    @action(detail=True, methods=['post'])
    def deliver(self, request, pk=None):
        """Mark sales order as delivered"""
        sales_order = self.get_object()
        
        if sales_order.status != 'SHIPPED':
            return Response(
                {'error': 'Only shipped orders can be marked as delivered'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        sales_order.status = 'DELIVERED'
        sales_order.save()
        
        return Response({'message': 'Sales order marked as delivered'})

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a sales order"""
        sales_order = self.get_object()
        
        if sales_order.status in ['DELIVERED', 'CANCELLED']:
            return Response(
                {'error': 'Cannot cancel delivered or already cancelled orders'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # If order was shipped, restore inventory
        if sales_order.status == 'SHIPPED':
            for item in sales_order.items.all():
                product = item.product
                product.stock_quantity += item.quantity
                product.save()
        
        sales_order.status = 'CANCELLED'
        sales_order.save()
        
        return Response({'message': 'Sales order cancelled successfully'})

    @action(detail=True, methods=['post'])
    def create_invoice(self, request, pk=None):
        """Create invoice from sales order"""
        sales_order = self.get_object()
        
        if hasattr(sales_order, 'invoice'):
            return Response(
                {'error': 'Invoice already exists for this sales order'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if sales_order.status not in ['CONFIRMED', 'SHIPPED', 'DELIVERED']:
            return Response(
                {'error': 'Sales order must be confirmed before creating invoice'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Calculate due date (30 days from now by default)
        due_date = timezone.now().date() + timedelta(days=30)
        
        invoice = Invoice.objects.create(
            sales_order=sales_order,
            customer=sales_order.customer,
            due_date=due_date,
            subtotal=sales_order.subtotal,
            discount_amount=sales_order.discount_amount,
            tax_amount=sales_order.tax_amount,
            total_amount=sales_order.total_amount,
            payment_terms=sales_order.customer.payment_terms,
            created_by=request.user
        )
        
        serializer = InvoiceSerializer(invoice)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def dashboard_stats(self, request):
        """Get sales order dashboard statistics"""
        today = timezone.now().date()
        this_month = today.replace(day=1)
        last_month = (this_month - timedelta(days=1)).replace(day=1)
        
        stats = {
            'total_orders': SalesOrder.objects.count(),
            'orders_this_month': SalesOrder.objects.filter(order_date__gte=this_month).count(),
            'orders_last_month': SalesOrder.objects.filter(
                order_date__gte=last_month,
                order_date__lt=this_month
            ).count(),
            'pending_orders': SalesOrder.objects.filter(status__in=['DRAFT', 'PENDING']).count(),
            'confirmed_orders': SalesOrder.objects.filter(status='CONFIRMED').count(),
            'total_sales_amount': SalesOrder.objects.aggregate(total=Sum('total_amount'))['total'] or 0,
            'sales_this_month': SalesOrder.objects.filter(
                order_date__gte=this_month
            ).aggregate(total=Sum('total_amount'))['total'] or 0,
        }
        
        return Response(stats)

class SalesOrderItemViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing sales order items
    """
    queryset = SalesOrderItem.objects.all().select_related('product', 'sales_order')
    serializer_class = SalesOrderItemSerializer
    permission_classes = [IsAdminOrSales]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['sales_order', 'product']
    ordering = ['id']

class InvoiceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing invoices
    """
    queryset = Invoice.objects.all().select_related('customer', 'sales_order')
    permission_classes = [IsAdminOrSales]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'customer', 'invoice_date']
    search_fields = ['invoice_number', 'customer__name', 'notes']
    ordering_fields = ['invoice_date', 'invoice_number', 'total_amount', 'due_date']
    ordering = ['-invoice_date', '-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return InvoiceListSerializer
        return InvoiceSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=['post'])
    def mark_sent(self, request, pk=None):
        """Mark invoice as sent"""
        invoice = self.get_object()
        invoice.status = 'SENT'
        invoice.save()
        return Response({'message': 'Invoice marked as sent'})

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        """Mark invoice as fully paid"""
        invoice = self.get_object()
        
        if invoice.balance_due <= 0:
            return Response(
                {'error': 'Invoice is already fully paid'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create payment record for remaining balance
        Payment.objects.create(
            invoice=invoice,
            amount=invoice.balance_due,
            payment_method=request.data.get('payment_method', 'OTHER'),
            reference_number=request.data.get('reference_number', ''),
            notes=request.data.get('notes', 'Marked as paid'),
            created_by=request.user
        )
        
        return Response({'message': 'Invoice marked as paid'})

    @action(detail=False, methods=['get'])
    def overdue(self, request):
        """Get overdue invoices"""
        today = timezone.now().date()
        overdue_invoices = Invoice.objects.filter(
            due_date__lt=today,
            status__in=['SENT', 'PARTIAL']
        ).select_related('customer')
        
        serializer = InvoiceListSerializer(overdue_invoices, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def dashboard_stats(self, request):
        """Get invoice dashboard statistics"""
        today = timezone.now().date()
        this_month = today.replace(day=1)
        
        stats = {
            'total_invoices': Invoice.objects.count(),
            'invoices_this_month': Invoice.objects.filter(invoice_date__gte=this_month).count(),
            'paid_invoices': Invoice.objects.filter(status='PAID').count(),
            'overdue_invoices': Invoice.objects.filter(
                due_date__lt=today,
                status__in=['SENT', 'PARTIAL']
            ).count(),
            'total_invoice_amount': Invoice.objects.aggregate(total=Sum('total_amount'))['total'] or 0,
            'total_outstanding': Invoice.objects.aggregate(total=Sum('balance_due'))['total'] or 0,
            'total_paid': Invoice.objects.aggregate(total=Sum('amount_paid'))['total'] or 0,
        }
        
        return Response(stats)

class PaymentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing payments
    """
    queryset = Payment.objects.all().select_related('invoice__customer')
    serializer_class = PaymentSerializer
    permission_classes = [IsAdminOrSales]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['payment_method', 'invoice', 'payment_date']
    search_fields = ['invoice__invoice_number', 'invoice__customer__name', 'reference_number', 'transaction_id']
    ordering_fields = ['payment_date', 'amount']
    ordering = ['-payment_date']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=False, methods=['get'])
    def dashboard_stats(self, request):
        """Get payment dashboard statistics"""
        today = timezone.now().date()
        this_month = today.replace(day=1)
        
        stats = {
            'total_payments': Payment.objects.count(),
            'payments_this_month': Payment.objects.filter(payment_date__gte=this_month).count(),
            'total_payment_amount': Payment.objects.aggregate(total=Sum('amount'))['total'] or 0,
            'payments_this_month_amount': Payment.objects.filter(
                payment_date__gte=this_month
            ).aggregate(total=Sum('amount'))['total'] or 0,
        }
        
        return Response(stats)


class DownPaymentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing customer down payments
    """
    queryset = DownPayment.objects.all()
    permission_classes = [IsAdminOrSales]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['customer', 'status', 'payment_method']
    search_fields = ['down_payment_number', 'customer__name', 'reference_number']
    ordering_fields = ['payment_date', 'amount', 'remaining_amount']
    ordering = ['-payment_date']

    def get_serializer_class(self):
        return DownPaymentSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by customer if specified
        customer_id = self.request.query_params.get('customer')
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)
        
        # Filter by status if specified
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter available down payments (for invoice creation)
        available_only = self.request.query_params.get('available_only')
        if available_only == 'true':
            queryset = queryset.filter(status='ACTIVE', remaining_amount__gt=0)
        
        return queryset

    @action(detail=False, methods=['get'])
    def customer_summary(self, request):
        """Get down payment summary for all customers"""
        customers = Customer.objects.annotate(
            total_down_payments=Count('down_payments'),
            total_available_amount=Sum('down_payments__remaining_amount', 
                                     filter=Q(down_payments__status='ACTIVE'))
        ).filter(total_down_payments__gt=0)
        
        serializer = CustomerDownPaymentSummarySerializer(customers, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def refund(self, request, pk=None):
        """Refund a down payment"""
        down_payment = self.get_object()
        
        if down_payment.status != 'ACTIVE':
            return Response(
                {'error': 'Only active down payments can be refunded'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if down_payment.used_amount > 0:
            return Response(
                {'error': 'Cannot refund partially used down payment'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        down_payment.status = 'REFUNDED'
        down_payment.save()
        
        return Response({'message': 'Down payment refunded successfully'})


class DownPaymentUsageViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing down payment usage tracking
    """
    queryset = DownPaymentUsage.objects.all()
    serializer_class = DownPaymentUsageSerializer
    permission_classes = [IsAdminOrSales]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['down_payment', 'sales_order', 'invoice']
    search_fields = ['down_payment__down_payment_number', 'down_payment__customer__name']
    ordering_fields = ['usage_date', 'amount_used']
    ordering = ['-usage_date']

    @action(detail=False, methods=['get'])
    def by_customer(self, request):
        """Get down payment usage by customer"""
        customer_id = request.query_params.get('customer')
        if not customer_id:
            return Response({'error': 'Customer ID is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        usages = self.get_queryset().filter(down_payment__customer_id=customer_id)
        serializer = self.get_serializer(usages, many=True)
        return Response(serializer.data)
