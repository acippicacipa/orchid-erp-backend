from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.db import models
from accounts.permissions import IsAdminOrPurchasing
from .models import Supplier, PurchaseOrder, PurchaseOrderItem, Bill, SupplierPayment
from .serializers import SupplierSerializer, SupplierListSerializer, PurchaseOrderSerializer, PurchaseOrderItemSerializer, BillSerializer, SupplierPaymentSerializer
from inventory.models import Product

class SupplierViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminOrPurchasing]
    queryset = Supplier.objects.all()
    
    def get_serializer_class(self):
        if self.action == 'list':
            return SupplierListSerializer
        return SupplierSerializer
    
    def get_queryset(self):
        queryset = Supplier.objects.all()
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset.order_by('name')

class PurchaseOrderViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminOrPurchasing]
    queryset = PurchaseOrder.objects.all()
    serializer_class = PurchaseOrderSerializer
    
    def get_queryset(self):
        queryset = PurchaseOrder.objects.select_related('supplier').prefetch_related('items__product')
        status_filter = self.request.query_params.get('status', None)
        supplier_id = self.request.query_params.get('supplier', None)
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if supplier_id:
            queryset = queryset.filter(supplier_id=supplier_id)
            
        return queryset.order_by('-order_date', '-created_at')
    
    def perform_create(self, serializer):
        # Auto-generate order number if not provided
        if not serializer.validated_data.get('order_number'):
            last_po = PurchaseOrder.objects.filter(order_number__startswith='PO').order_by('-order_number').first()
            if last_po and last_po.order_number:
                try:
                    last_num = int(last_po.order_number.replace('PO', ''))
                    new_num = last_num + 1
                except:
                    new_num = 1
            else:
                new_num = 1
            serializer.validated_data['order_number'] = f'PO{new_num:06d}'
        
        # Calculate total amount
        items_data = serializer.validated_data.get('items', [])
        total_amount = sum(item['line_total'] for item in items_data)
        
        serializer.save(
            created_by=self.request.user,
            total_amount=total_amount
        )
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """
        Approve a DRAFT Purchase Order.
        """
        purchase_order = self.get_object()
        if purchase_order.status != 'DRAFT':
            return Response(
                {'error': f'Only DRAFT orders can be approved. Current status is {purchase_order.status}.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update status dan data approval
        purchase_order.status = 'CONFIRMED'
        purchase_order.approved_by = request.user
        # Anda juga bisa menambahkan tanggal approval jika ada field-nya
        # purchase_order.approved_at = timezone.now() 
        
        purchase_order.save()
        
        # Kembalikan data PO yang sudah diupdate agar frontend bisa langsung refresh
        serializer = self.get_serializer(purchase_order)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def receive(self, request, pk=None):
        """Mark purchase order as received and update inventory"""
        purchase_order = self.get_object()
        if purchase_order.status != 'CONFIRMED':
            return Response({'error': 'Only confirmed orders can be received'}, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            # Update purchase order status
            purchase_order.status = 'RECEIVED'
            purchase_order.save()
            
            # Update product stock quantities
            for item in purchase_order.items.all():
                # Update product stock
                item.product.stock_quantity += item.quantity
                item.product.save()
        
        return Response({'message': 'Purchase order received and inventory updated'})
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a purchase order"""
        purchase_order = self.get_object()
        if purchase_order.status in ['RECEIVED', 'CANCELLED']:
            return Response({'error': 'Cannot cancel received or already cancelled orders'}, status=status.HTTP_400_BAD_REQUEST)
        
        purchase_order.status = 'CANCELLED'
        purchase_order.save()
        
        return Response({'message': 'Purchase order cancelled successfully'})

class PurchaseOrderItemViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminOrPurchasing]
    queryset = PurchaseOrderItem.objects.all()
    serializer_class = PurchaseOrderItemSerializer

class BillViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminOrPurchasing]
    queryset = Bill.objects.all()
    serializer_class = BillSerializer
    
    def get_queryset(self):
        queryset = Bill.objects.select_related('supplier', 'purchase_order')
        status_filter = self.request.query_params.get('status', None)
        supplier_id = self.request.query_params.get('supplier', None)
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if supplier_id:
            queryset = queryset.filter(supplier_id=supplier_id)
            
        return queryset.order_by('-bill_date', '-created_at')
    
    def perform_create(self, serializer):
        # Ambil total_amount dari data yang sudah divalidasi
        total_amount = serializer.validated_data.get('total_amount', 0)
        
        # Atur balance_due secara otomatis
        serializer.validated_data['balance_due'] = total_amount
        
        # ==============================================================================
        # PERBAIKAN LOGIKA PEMBUATAN NOMOR BILL
        # ==============================================================================
        
        # Dapatkan bill terakhir berdasarkan ID untuk mendapatkan nomor urut berikutnya
        last_bill = Bill.objects.all().order_by('id').last()
        
        if last_bill:
            # Ambil ID dari bill terakhir dan tambahkan 1
            new_id = last_bill.id + 1
        else:
            # Jika ini adalah bill pertama di database
            new_id = 1
            
        # Buat nomor bill baru yang terjamin unik
        new_bill_number = f'BILL-{new_id:06d}'
        
        # Set nomor bill di data yang akan disimpan
        serializer.validated_data['bill_number'] = new_bill_number
        
        # Simpan objek dengan data yang sudah dimodifikasi
        serializer.save()
    
    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        """Mark a bill as fully paid"""
        bill = self.get_object()
        if bill.status == 'PAID':
            return Response({'error': 'Bill is already marked as paid'}, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            # Create payment record for remaining balance
            remaining_balance = bill.balance_due
            if remaining_balance > 0:
                SupplierPayment.objects.create(
                    bill=bill,
                    amount=remaining_balance,
                    payment_method='BANK_TRANSFER',
                    notes='Marked as paid via system'
                )
            
            # Update bill status
            bill.amount_paid = bill.total_amount
            bill.balance_due = 0
            bill.status = 'PAID'
            bill.save()
        
        return Response({'message': 'Bill marked as paid successfully'})

class SupplierPaymentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminOrPurchasing]
    queryset = SupplierPayment.objects.all()
    serializer_class = SupplierPaymentSerializer
    
    def get_queryset(self):
        queryset = SupplierPayment.objects.select_related('bill__supplier')
        bill_id = self.request.query_params.get('bill', None)
        
        if bill_id:
            queryset = queryset.filter(bill_id=bill_id)
            
        return queryset.order_by('-payment_date', '-created_at')
    
    def perform_create(self, serializer):
        with transaction.atomic():
            payment = serializer.save()
            
            # Update bill payment status
            bill = payment.bill
            total_payments = bill.payments.aggregate(total=models.Sum('amount'))['total'] or 0
            bill.amount_paid = total_payments
            bill.balance_due = bill.total_amount - total_payments
            
            # Update bill status based on payment
            if bill.balance_due <= 0:
                bill.status = 'PAID'
            elif bill.amount_paid > 0:
                bill.status = 'PENDING'
            
            bill.save()
