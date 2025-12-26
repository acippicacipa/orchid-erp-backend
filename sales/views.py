from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, F, ExpressionWrapper, DecimalField, Q, OuterRef, Subquery, Value, Case, When
from django.db.models.functions import Coalesce
from django.db import transaction
from django.utils import timezone
from datetime import datetime, timedelta
from accounts.permissions import IsAdminOrSales
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from inventory.models import Stock, Location, StockMovement
from .filters import SalesOrderFilter
from .services import PricingService
from .models import ( 
    Customer, CustomerGroup, Product, SalesOrder, SalesOrderItem, Invoice, Payment, DownPayment, 
    DownPaymentUsage, DeliveryOrder, SalesReturn, 
    ConsignmentShipment, ConsignmentShipmentItem, ConsignmentSalesReport, ConsignmentSalesReportItem
)
from .serializers import (
    CustomerSerializer, CustomerListSerializer, CustomerGroupSerializer,
    SalesOrderSerializer, SalesOrderListSerializer, SalesOrderItemSerializer,
    InvoiceSerializer, InvoiceListSerializer, PaymentSerializer,
    ProductSearchSerializer, DownPaymentSerializer, DownPaymentUsageSerializer,
    CustomerDownPaymentSummarySerializer, DeliveryOrderSerializer, CreateConsolidatedInvoiceSerializer, InvoicePrintItemSerializer,
    SalesReturnSerializer, ConsignmentShipmentSerializer, ConsignmentSalesReportSerializer
)
from accounting.models import JournalEntry, JournalEntryLine, Account
from inventory.models import StockMovement, Location, Product, Stock
from decimal import Decimal, InvalidOperation
from collections import defaultdict

def calculate_due_date(base_date, payment_terms_str):
    """
    Menghitung tanggal jatuh tempo berdasarkan string payment terms.
    Contoh: 'Net 30 days' -> base_date + 30 hari.
    """
    try:
        # Coba ekstrak angka dari string, misal "Net 30 days" -> "30"
        days_str = ''.join(filter(str.isdigit, payment_terms_str))
        if days_str:
            days = int(days_str)
            return base_date + timedelta(days=days)
    except (ValueError, TypeError):
        # Jika gagal (misal, payment_terms adalah 'Cash on Delivery'),
        # kembalikan tanggal dasar.
        pass
    
    # Default jika tidak ada angka atau format tidak dikenali
    return base_date

class DeliveryOrderViewSet(viewsets.ModelViewSet):
    queryset = DeliveryOrder.objects.select_related('sales_order__customer').all()
    serializer_class = DeliveryOrderSerializer
    permission_classes = [IsAdminOrSales] # Sesuaikan permission
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['status', 'carrier']
    search_fields = ['do_number', 'sales_order__order_number', 'tracking_number']

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
    
    def get_queryset(self):
        """
        Optimalkan queryset dengan anotasi untuk menghindari N+1 query.
        """
        queryset = Customer.objects.select_related('customer_group').annotate(
            # Hitung total balance_due dari invoice yang relevan
            total_outstanding=Sum(
                'invoices__balance_due',
                filter=Q(invoices__status__in=['SENT', 'PARTIAL', 'OVERDUE', 'DRAFT'])
            )
        ).annotate(
            # Buat field 'outstanding_balance' dari hasil anotasi
            outstanding_balance_calc=ExpressionWrapper(
                F('total_outstanding'), output_field=DecimalField()
            ),
            # Hitung 'available_credit' langsung di database
            available_credit_calc=ExpressionWrapper(
                F('credit_limit') - F('total_outstanding'), output_field=DecimalField()
            )
        )
        return queryset

    @action(detail=False, methods=['get'])
    def search(self, request):
        """Search customers for dropdown selection"""
        query = request.query_params.get('q', '')
        if len(query) < 3:
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
    queryset = SalesOrder.objects.select_related(
        'customer', 
        'customer__customer_group' # Jika Anda butuh info grup di customer_details
    ).prefetch_related(
        'items', 
        'items__product' # Ambil semua item dan produk terkait dalam 2 query
    ).all()
    permission_classes = [IsAdminOrSales]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = SalesOrderFilter
    search_fields = ['order_number', 'customer__name']
    ordering_fields = ['order_date', 'order_number', 'total_amount', 'created_at']
    ordering = ['-order_date', '-created_at']

    def get_serializer_class(self):
        if self.action == 'list' or self.action == 'retrieve':
            return SalesOrderListSerializer
        return SalesOrderSerializer

    def perform_create(self, serializer):
        sales_order = serializer.save(created_by=self.request.user)

        if sales_order.down_payment_amount > 0:
            # Jika ada DP, ubah status menjadi Partially Paid
            sales_order.status = 'PARTIALLY_PAID'
            sales_order.save()
            
        # --- LOGIKA OTOMATIS UNTUK PENJUALAN TUNAI ---
        if sales_order.customer.payment_type == 'CASH' and sales_order.amount_paid >= sales_order.total_amount:
            # 1. Buat Invoice secara otomatis
            invoice = Invoice.objects.create(
                sales_order=sales_order,
                customer=sales_order.customer,
                invoice_date=sales_order.order_date,
                due_date=sales_order.order_date, # Jatuh tempo hari ini
                total_amount=sales_order.total_amount,
                amount_paid=sales_order.amount_paid,
                status='PAID', # Langsung lunas
                created_by=self.request.user
            )

            # 2. Buat record Payment secara otomatis
            Payment.objects.create(
                invoice=invoice,
                payment_date=sales_order.order_date,
                amount=sales_order.amount_paid,
                payment_method=sales_order.payment_method,
                created_by=self.request.user
            )
            
            # 3. (Opsional) Update status SO menjadi 'DELIVERED' atau 'COMPLETED'
            sales_order.status = 'DELIVERED'
            sales_order.save()

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=['post'], url_path='confirm')
    def confirm_order(self, request, pk=None):
        sales_order = self.get_object()
        customer = sales_order.customer

        if sales_order.status != 'DRAFT':
            return Response({'error': 'Only DRAFT orders can be confirmed.'}, status=status.HTTP_400_BAD_REQUEST)

        # --- LOGIKA PENGECEKAN KREDIT ---
        # Cek jika customer memiliki limit kredit (jika limit 0, dianggap tidak terbatas)
        if customer.credit_limit > 0:
            # Hitung total utang jika SO ini dikonfirmasi
            projected_balance = customer.outstanding_balance + sales_order.total_amount
            
            if projected_balance > customer.credit_limit:
                # Jika over limit, ubah status dan beri pesan
                sales_order.status = 'PENDING_APPROVAL'
                sales_order.save()
                
                # Di sini Anda bisa menambahkan logika untuk mengirim notifikasi ke pimpinan
                # send_approval_notification(sales_order)
                
                return Response({
                    'message': 'Order exceeds credit limit and has been sent for approval.',
                    'status': 'PENDING_APPROVAL'
                }, status=status.HTTP_202_ACCEPTED) # Gunakan status 202 Accepted

        # Jika tidak over limit, langsung konfirmasi
        sales_order.status = 'CONFIRMED'
        sales_order.save()
        
        return Response({
            'message': 'Sales order has been confirmed successfully.',
            'status': 'CONFIRMED'
        })

    @action(detail=True, methods=['post'], url_path='approve', permission_classes=[IsAdminUser])
    def approve_order(self, request, pk=None):
        sales_order = self.get_object()
        if sales_order.status != 'PENDING_APPROVAL':
            return Response({'error': 'Only orders pending approval can be approved.'}, status=status.HTTP_400_BAD_REQUEST)

        sales_order.status = 'CONFIRMED'
        sales_order.approved_by = request.user
        sales_order.approved_at = timezone.now()
        sales_order.save()
        return Response({'message': 'Sales order approved and confirmed.'})

    @action(detail=True, methods=['post'], url_path='reject', permission_classes=[IsAdminUser])
    def reject_order(self, request, pk=None):
        sales_order = self.get_object()
        if sales_order.status != 'PENDING_APPROVAL':
            return Response({'error': 'Only orders pending approval can be rejected.'}, status=status.HTTP_400_BAD_REQUEST)

        sales_order.status = 'REJECTED'
        sales_order.rejection_reason = request.data.get('reason', 'No reason provided.')
        sales_order.save()
        return Response({'message': 'Sales order has been rejected.'})

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

    @action(detail=True, methods=['post'], url_path='start_processing')
    @transaction.atomic # Gunakan transaksi atomik untuk memastikan integritas data
    def start_processing(self, request, pk=None):
        sales_order = self.get_object()

        if sales_order.status != 'CONFIRMED':
            return Response({'error': 'Only CONFIRMED orders can be processed.'}, status=status.HTTP_400_BAD_REQUEST)

        # Logika Alokasi Stok
        for item in sales_order.items.all():
            try:
                # Asumsi Anda memiliki satu lokasi gudang utama atau logika untuk menentukannya
                # Ganti dengan logika penentuan lokasi yang sesuai
                stock_location = Location.objects.filter(location_type='WAREHOUSE').first()
                if not stock_location:
                    raise Exception("Main warehouse location not found.")

                stock = Stock.objects.get(product=item.product, location=stock_location)
                
                # Cek apakah stok yang bisa dijual mencukupi
                if stock.quantity_sellable < item.quantity:
                    return Response({
                        'error': f'Insufficient sellable stock for {item.product.name}. Required: {item.quantity}, Available: {stock.quantity_sellable}'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                # Alokasikan stok
                stock.quantity_allocated += item.quantity
                stock.save()

            except Stock.DoesNotExist:
                return Response({'error': f'Stock record not found for {item.product.name}.'}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                 return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Jika semua alokasi berhasil, ubah status SO
        sales_order.status = 'PROCESSING'
        sales_order.save()

        return Response({'message': 'Order is now being processed and stock has been allocated.'})

    @action(detail=True, methods=['post'], url_path='record_picking')
    @transaction.atomic
    def record_picking(self, request, pk=None):
        sales_order = self.get_object()
        items_data = request.data.get('items', []) # Frontend mengirim array item dengan picked qty

        if sales_order.status != 'PROCESSING':
            return Response({'error': 'Can only record picking for PROCESSING orders.'}, status=status.HTTP_400_BAD_REQUEST)

        for item_data in items_data:
            try:
                order_item = SalesOrderItem.objects.get(id=item_data['id'], sales_order=sales_order)
                
                picked_qty = Decimal(item_data['actual_picked_quantity'])

                if picked_qty > order_item.quantity:
                    raise serializers.ValidationError(f"Picked quantity for {order_item.product.name} cannot exceed required quantity.")
                
                # Update picked_quantity
                order_item.picked_quantity = picked_qty
                order_item.save()

            except SalesOrderItem.DoesNotExist:
                # Abaikan jika item tidak ditemukan, atau log error
                pass
            except (KeyError, ValueError, TypeError):
                return Response({'error': 'Invalid item data provided.'}, status=status.HTTP_400_BAD_REQUEST)

        total_picked_value = sales_order.items.annotate(
            line_picked_total=ExpressionWrapper(
                F('picked_quantity') * F('unit_price') * (Decimal('1.0') - F('discount_percentage') / Decimal('100.0')),
                output_field=DecimalField()
            )
        ).aggregate(
            total=Sum('line_picked_total')
        )['total'] or Decimal('0.00')

        # Update field di SalesOrder
        sales_order.picked_subtotal = total_picked_value
        sales_order.save()

        # Ambil ulang data SO setelah diupdate untuk dikirim kembali
        sales_order.refresh_from_db()
        serializer = self.get_serializer(sales_order)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='create_delivery_order')
    @transaction.atomic
    def create_delivery_order(self, request, pk=None):
        sales_order = self.get_object()
        
        if sales_order.status != 'PROCESSING':
            return Response({'error': 'Only PROCESSING orders can be shipped.'}, status=status.HTTP_400_BAD_REQUEST)

        if sales_order.fulfillment_status == 'UNFULFILLED':
            return Response({
                'error': 'Cannot create Delivery Order because no items have been picked yet. Please record picked quantities first.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 1. Buat Delivery Order
        do_data = request.data
        delivery_order = DeliveryOrder.objects.create(
            sales_order=sales_order,
            carrier=do_data.get('carrier'),
            tracking_number=do_data.get('tracking_number'),
            notes=do_data.get('notes'),
            created_by=request.user
        )

        # 2. Kurangi Stok Fisik (Post-Goods Issue)
        for item in sales_order.items.all():
            try:
                # Tentukan lokasi gudang (sesuaikan dengan logika Anda)
                stock_location = Location.objects.filter(location_type='WAREHOUSE').first()
                stock = Stock.objects.get(product=item.product, location=stock_location)
                
                # Kurangi stok fisik dan alokasi
                stock.quantity_on_hand -= item.quantity
                stock.quantity_allocated -= item.quantity
                stock.save()

                # Buat catatan pergerakan stok
                StockMovement.objects.create(
                    product=item.product,
                    location=stock_location,
                    movement_type='SALE',
                    quantity=-item.quantity, # Kuantitas negatif karena barang keluar
                    reference_number=sales_order.order_number,
                    reference_type='SALES_ORDER',
                    user=request.user
                )
            except Stock.DoesNotExist:
                # Seharusnya tidak terjadi karena stok sudah dialokasikan,
                # tapi ini sebagai pengaman.
                raise serializers.ValidationError(f"Stock for {item.product.name} not found during shipping.")

        # 3. Ubah status Sales Order menjadi SHIPPED
        sales_order.status = 'SHIPPED'
        sales_order.save()

        serializer = DeliveryOrderSerializer(delivery_order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

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

    @action(detail=False, methods=['get'], url_path='shortage_summary')
    def shortage_summary(self, request):
        # Ambil semua item yang outstanding > 0
        shortage_items = SalesOrderItem.objects.filter(
            quantity__gt=F('picked_quantity')
        ).values(
            'product__id', 'product__name', 'product__sku'
        ).annotate(
            total_shortage=Sum(F('quantity') - F('picked_quantity'))
        ).order_by('-total_shortage')
        
        return Response(shortage_items)

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

    @action(detail=False, methods=['post'], url_path='create-consolidated')
    @transaction.atomic
    def create_consolidated_invoice(self, request):
        """
        Membuat satu invoice dari satu atau lebih Sales Order.
        """
        serializer = CreateConsolidatedInvoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        validated_data = serializer.validated_data
        customer_id = validated_data['customer_id']
        so_ids = validated_data['sales_order_ids']
        
        customer = Customer.objects.get(id=customer_id)
        orders_to_invoice = SalesOrder.objects.filter(id__in=so_ids)

        total_picked_subtotal = Decimal('0.00')
        total_order_discount = Decimal('0.00')
        total_tax = Decimal('0.00')
        total_shipping = Decimal('0.00')

        # Kita perlu loop untuk menghitung diskon dan pajak per-order secara akurat
        for order in orders_to_invoice:
            # 1. Ambil subtotal yang sudah di-pick dari field SO
            current_picked_subtotal = order.picked_subtotal or Decimal('0.00')
            
            # 2. Hitung diskon level order berdasarkan subtotal yang di-pick
            current_order_discount = current_picked_subtotal * (order.discount_percentage / Decimal('100.0'))
            
            # 3. Hitung jumlah kena pajak (taxable amount)
            taxable_amount = current_picked_subtotal - current_order_discount
            
            # 4. Hitung pajak berdasarkan jumlah kena pajak
            current_order_tax = taxable_amount * (order.tax_percentage / Decimal('100.0'))

            # 5. Akumulasikan semua nilai
            total_picked_subtotal += current_picked_subtotal
            total_order_discount += current_order_discount
            total_tax += current_order_tax
            total_shipping += order.shipping_cost

        # 6. Hitung Grand Total untuk Invoice
        grand_total = total_picked_subtotal - total_order_discount + total_tax + total_shipping

        invoice_date = timezone.now().date()
        
        # 1. Ambil payment_terms dari customer
        payment_terms = customer.payment_terms
        
        # 2. Hitung due_date menggunakan fungsi helper
        due_date = calculate_due_date(invoice_date, payment_terms)

        # Buat Invoice baru dengan nilai gabungan yang sudah dihitung
        new_invoice = Invoice.objects.create(
            customer=customer,
            invoice_date=invoice_date,
            due_date=due_date,
            notes=validated_data.get('notes', ''),
            
            # Simpan nilai-nilai gabungan ini di invoice
            subtotal=total_picked_subtotal,
            discount_amount=total_order_discount,
            tax_amount=total_tax,
            # Anda mungkin perlu field 'shipping_amount' di model Invoice jika ingin menyimpannya terpisah
            total_amount=grand_total,
            
            created_by=request.user
        )

        # Tautkan invoice baru ke semua SO yang dipilih
        # Asumsi: Anda sudah mengubah relasi di model Invoice menjadi ManyToManyField
        new_invoice.sales_orders.set(orders_to_invoice)

        # Kirim kembali data invoice yang baru dibuat
        response_serializer = InvoiceSerializer(new_invoice)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='print-details')
    def print_details(self, request, pk=None):
        """
        Mengembalikan data invoice lengkap dengan item yang sudah digabungkan
        untuk keperluan cetak.
        """
        invoice = self.get_object()
        
        # Ambil semua item dari semua sales order yang terkait dengan invoice ini
        order_items = SalesOrderItem.objects.filter(
            sales_order__in=invoice.sales_orders.all()
        ).select_related('product')

        # Gunakan defaultdict untuk menggabungkan item dengan produk yang sama
        consolidated_items = defaultdict(lambda: {
            'product_id': None,
            'product_sku': '',
            'product_name': '',
            'total_picked_quantity': Decimal('0.00'),
            'unit_price': Decimal('0.00'), # Asumsi harga sama
            'discount_percentage': Decimal('0.00'), # Asumsi diskon sama
        })

        for item in order_items:
            # Hanya proses item yang benar-benar di-pick
            if item.picked_quantity > 0:
                key = item.product_id
                
                # Isi detail produk jika ini pertama kali
                if not consolidated_items[key]['product_id']:
                    consolidated_items[key]['product_id'] = item.product.id
                    consolidated_items[key]['product_sku'] = item.product.sku
                    consolidated_items[key]['product_name'] = item.product.name
                    consolidated_items[key]['unit_price'] = item.unit_price
                    consolidated_items[key]['discount_percentage'] = item.discount_percentage

                # Jumlahkan kuantitas yang di-pick
                consolidated_items[key]['total_picked_quantity'] += item.picked_quantity

        # Hitung total untuk setiap item yang sudah digabungkan
        final_items_list = []
        for item_data in consolidated_items.values():
            subtotal = item_data['total_picked_quantity'] * item_data['unit_price']
            discount_amount = subtotal * (item_data['discount_percentage'] / Decimal('100.0'))
            total = subtotal - discount_amount
            
            item_data['line_subtotal'] = subtotal
            item_data['line_discount_amount'] = discount_amount
            item_data['line_total'] = total
            final_items_list.append(item_data)

        # Siapkan data invoice utama
        invoice_serializer = InvoiceSerializer(invoice)
        
        # Siapkan data item yang sudah digabungkan
        items_serializer = InvoicePrintItemSerializer(final_items_list, many=True)

        # Gabungkan semuanya dalam satu respons
        response_data = {
            'invoice': invoice_serializer.data,
            'items': items_serializer.data
        }
        
        return Response(response_data)

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

class SalesReturnViewSet(viewsets.ModelViewSet):
    queryset = SalesReturn.objects.all().select_related(
        'customer', 'invoice', 'created_by', 'items_received_by', 'return_location'
    ).prefetch_related('items__product').order_by('-return_date')
    serializer_class = SalesReturnSerializer
    permission_classes = [IsAuthenticated] # Ganti dengan permission yang sesuai
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['customer', 'status', 'return_location']
    search_fields = ['return_number', 'customer__name', 'invoice__invoice_number']

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def approve(self, request, pk=None):
        """Menyetujui Sales Return dan membuat jurnal pembalik pendapatan."""
        sales_return = self.get_object()
        if sales_return.status != 'DRAFT':
            return Response({'error': 'Only DRAFT returns can be approved.'}, status=status.HTTP_400_BAD_REQUEST)

        # --- JURNAL AKUNTANSI 1: PEMBALIK PENDAPATAN ---
        try:
            # Ambil akun-akun yang relevan dari settings atau model lain
            sales_return_account = Account.objects.get(code='4-2000') # Contoh: Akun Retur Penjualan
            ar_account = Account.objects.get(code='1-1200') # Contoh: Akun Piutang Usaha
        except Account.DoesNotExist:
            return Response({'error': 'Accounting accounts for sales return are not configured.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        journal = JournalEntry.objects.create(
            entry_date=timezone.now().date(),
            entry_type='SALES_RETURN',
            description=f"Sales Return {sales_return.return_number} from {sales_return.customer.name}",
            created_by=request.user
        )
        # DEBIT: Retur Penjualan
        JournalEntryLine.objects.create(journal_entry=journal, account=sales_return_account, debit_amount=sales_return.total_amount)
        # KREDIT: Piutang Usaha
        JournalEntryLine.objects.create(journal_entry=journal, account=ar_account, credit_amount=sales_return.total_amount)
        
        journal.total_debit = sales_return.total_amount
        journal.total_credit = sales_return.total_amount
        journal.status = 'POSTED'
        journal.save()
        # ------------------------------------------------

        sales_return.status = 'APPROVED'
        sales_return.save()
        return Response(self.get_serializer(sales_return).data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def complete(self, request, pk=None):
        """Menyelesaikan retur: menerima barang, update stok, dan membuat jurnal pembalik HPP."""
        sales_return = self.get_object()
        if sales_return.status != 'APPROVED':
            return Response({'error': 'Only APPROVED returns can be completed.'}, status=status.HTTP_400_BAD_REQUEST)

        # --- JURNAL AKUNTANSI 2: PEMBALIK HPP ---
        try:
            cogs_account = Account.objects.get(code='5-1000') # Contoh: Akun HPP
            inventory_account = Account.objects.get(code='1-1300') # Contoh: Akun Persediaan
        except Account.DoesNotExist:
            return Response({'error': 'Accounting accounts for COGS reversal are not configured.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        total_cost = Decimal('0.00')
        for item in sales_return.items.all():
            # Buat Stock Movement
            StockMovement.objects.create(
                product=item.product,
                location=sales_return.return_location,
                movement_type='SALES_RETURN',
                quantity=item.quantity, # Kuantitas positif karena barang masuk kembali
                unit_cost=item.product.cost_price or 0,
                reference_number=sales_return.return_number,
                user=request.user
            )
            total_cost += item.quantity * (item.product.cost_price or 0)

        if total_cost > 0:
            journal = JournalEntry.objects.create(
                entry_date=timezone.now().date(),
                entry_type='SALES_RETURN_COGS',
                description=f"COGS Reversal for SR {sales_return.return_number}",
                created_by=request.user
            )
            # DEBIT: Persediaan
            JournalEntryLine.objects.create(journal_entry=journal, account=inventory_account, debit_amount=total_cost)
            # KREDIT: HPP
            JournalEntryLine.objects.create(journal_entry=journal, account=cogs_account, credit_amount=total_cost)
            
            journal.total_debit = total_cost
            journal.total_credit = total_cost
            journal.status = 'POSTED'
            journal.save()
        # --------------------------------------------

        sales_return.status = 'COMPLETED'
        sales_return.items_received_by = request.user
        sales_return.items_received_date = timezone.now()
        sales_return.save()
        return Response(self.get_serializer(sales_return).data)

class ConsignmentShipmentViewSet(viewsets.ModelViewSet):
    queryset = ConsignmentShipment.objects.all()
    serializer_class = ConsignmentShipmentSerializer # Anda perlu membuat serializer ini
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def ship(self, request, pk=None):
        shipment = self.get_object()
        if shipment.status != 'DRAFT':
            return Response({'error': 'Only DRAFT shipments can be shipped.'}, status=status.HTTP_400_BAD_REQUEST)

        # Buat Stock Movement (Transfer)
        for item in shipment.items.all():
            # Keluar dari gudang asal
            StockMovement.objects.create(
                product=item.product, location=shipment.from_location, movement_type='TRANSFER_OUT',
                quantity=-item.quantity, reference_number=shipment.shipment_number, user=request.user
            )
            # Masuk ke lokasi konsinyasi
            StockMovement.objects.create(
                product=item.product, location=shipment.to_consignment_location, movement_type='TRANSFER_IN',
                quantity=item.quantity, reference_number=shipment.shipment_number, user=request.user
            )
        
        shipment.status = 'SHIPPED'
        shipment.shipped_by = request.user # Asumsi ada field ini
        shipment.shipped_date = timezone.now() # Asumsi ada field ini
        shipment.save()
        return Response(self.get_serializer(shipment).data)

class ConsignmentSalesReportViewSet(viewsets.ModelViewSet):
    queryset = ConsignmentSalesReport.objects.all()
    serializer_class = ConsignmentSalesReportSerializer # Anda perlu membuat serializer ini
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def confirm(self, request, pk=None):
        report = self.get_object()
        if report.status != 'DRAFT':
            return Response({'error': 'Only DRAFT reports can be confirmed.'}, status=status.HTTP_400_BAD_REQUEST)

        total_cogs = Decimal('0.00')
        # 1. Buat Stock Movement (SALE) dari lokasi konsinyasi
        for item in report.items.all():
            StockMovement.objects.create(
                product=item.product, location=report.consignment_location, movement_type='SALE',
                quantity=-item.quantity_sold, reference_number=report.report_number, user=request.user
            )
            total_cogs += item.quantity_sold * (item.product.cost_price or 0)

        # 2. Buat Jurnal Penjualan
        ar_account = Account.objects.get(code='1-1200') # Piutang Usaha
        sales_account = Account.objects.get(code='4-1000') # Pendapatan Penjualan
        
        journal_sales = JournalEntry.objects.create(
            entry_date=report.report_date, entry_type='SALE',
            description=f"Consignment Sales from report {report.report_number}",
            created_by=request.user, total_debit=report.total_sales_amount, total_credit=report.total_sales_amount, status='POSTED'
        )
        JournalEntryLine.objects.create(journal_entry=journal_sales, account=ar_account, debit_amount=report.total_sales_amount)
        JournalEntryLine.objects.create(journal_entry=journal_sales, account=sales_account, credit_amount=report.total_sales_amount)

        # 3. Buat Jurnal HPP
        cogs_account = Account.objects.get(code='5-1000') # HPP
        inventory_account = Account.objects.get(code='1-1300') # Persediaan
        
        journal_cogs = JournalEntry.objects.create(
            entry_date=report.report_date, entry_type='SALE_COGS',
            description=f"COGS for Consignment Sales {report.report_number}",
            created_by=request.user, total_debit=total_cogs, total_credit=total_cogs, status='POSTED'
        )
        JournalEntryLine.objects.create(journal_entry=journal_cogs, account=cogs_account, debit_amount=total_cogs)
        JournalEntryLine.objects.create(journal_entry=journal_cogs, account=inventory_account, credit_amount=total_cogs)

        # Update status laporan
        report.status = 'CONFIRMED'
        report.total_cogs_amount = total_cogs
        report.save()
        
        # 4. Buat Invoice (opsional, tapi praktik yang baik)
        Invoice.objects.create(
            customer=report.customer, sales_order=None, # Tidak ada SO langsung
            invoice_date=report.report_date, due_date=report.report_date + timedelta(days=30), # Asumsi Net 30
            total_amount=report.total_sales_amount, status='PENDING',
            notes=f"Auto-generated from Consignment Sales Report {report.report_number}"
        )

        return Response(self.get_serializer(report).data)