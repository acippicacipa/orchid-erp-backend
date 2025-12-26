from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.db import models
from django.db.models import Q
from accounts.permissions import IsAdminOrPurchasing
from .models import (
    Supplier, PurchaseOrder, PurchaseOrderItem, Bill, SupplierPayment, PurchaseReturn, 
    ConsignmentReceipt, ConsignmentReceiptItem
)
from .serializers import (
    SupplierSerializer, SupplierListSerializer, PurchaseOrderSerializer, PurchaseOrderItemSerializer, 
    BillSerializer, SupplierPaymentSerializer, PurchaseReturnSerializer, ConsignmentReceiptSerializer
)
from inventory.models import Product, StockMovement, Stock
from accounting.models import JournalEntry, JournalEntryLine, Account
from decimal import Decimal
from django_filters.rest_framework import DjangoFilterBackend

class SupplierViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Supplier.objects.all()
    
    def get_serializer_class(self):
        if self.action == 'list':
            return SupplierListSerializer
        return SupplierSerializer
    
    def get_queryset(self):
        queryset = Supplier.objects.all()
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(contact_person__icontains=search)
            )
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

class PurchaseReturnViewSet(viewsets.ModelViewSet):
    queryset = PurchaseReturn.objects.all().select_related(
        'supplier', 'bill', 'created_by', 'items_shipped_by', 'return_from_location'
    ).prefetch_related('items__product').order_by('-return_date')
    serializer_class = PurchaseReturnSerializer
    permission_classes = [IsAdminOrPurchasing] # Ganti dengan permission yang sesuai
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['supplier', 'status', 'return_from_location']
    search_fields = ['return_number', 'supplier__name', 'bill__bill_number']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def approve(self, request, pk=None):
        """Menyetujui Purchase Return dan membuat jurnal pembalik utang."""
        purchase_return = self.get_object()
        if purchase_return.status != 'DRAFT':
            return Response({'error': 'Only DRAFT returns can be approved.'}, status=status.HTTP_400_BAD_REQUEST)

        # --- JURNAL AKUNTANSI 1: PEMBALIK UTANG ---
        try:
            ap_account = Account.objects.get(code='2-1100') # Contoh: Akun Utang Usaha
            # Buat akun kontra-persediaan jika belum ada
            purchase_return_account, _ = Account.objects.get_or_create(
                code='1-1399', 
                defaults={
                    'name': 'Purchase Returns Clearing', 
                    'account_type_id': 1, # Asumsi ID 1 adalah Aset
                    'description': 'Akun sementara untuk retur pembelian'
                }
            )
        except Account.DoesNotExist:
            return Response({'error': 'Accounting accounts for purchase return are not configured.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        journal = JournalEntry.objects.create(
            entry_date=timezone.now().date(),
            entry_type='PURCHASE_RETURN',
            description=f"Purchase Return {purchase_return.return_number} to {purchase_return.supplier.name}",
            created_by=request.user
        )
        # DEBIT: Utang Usaha
        JournalEntryLine.objects.create(journal_entry=journal, account=ap_account, debit_amount=purchase_return.total_amount)
        # KREDIT: Akun Kliring Retur Pembelian
        JournalEntryLine.objects.create(journal_entry=journal, account=purchase_return_account, credit_amount=purchase_return.total_amount)
        
        journal.total_debit = purchase_return.total_amount
        journal.total_credit = purchase_return.total_amount
        journal.status = 'POSTED'
        journal.save()
        # ------------------------------------------------

        purchase_return.status = 'APPROVED'
        purchase_return.save()
        return Response(self.get_serializer(purchase_return).data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def ship(self, request, pk=None):
        """Menyelesaikan retur: mengirim barang, update stok, dan membuat jurnal pengeluaran stok."""
        purchase_return = self.get_object()
        if purchase_return.status != 'APPROVED':
            return Response({'error': 'Only APPROVED returns can be shipped.'}, status=status.HTTP_400_BAD_REQUEST)

        # --- JURNAL AKUNTANSI 2: PENGELUARAN STOK ---
        try:
            inventory_account = Account.objects.get(code='1-1300') # Contoh: Akun Persediaan
            purchase_return_account = Account.objects.get(code='1-1399') # Akun kliring yang dibuat sebelumnya
        except Account.DoesNotExist:
            return Response({'error': 'Accounting accounts for stock reversal are not configured.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        total_cost = Decimal('0.00')
        for item in purchase_return.items.all():
            # Buat Stock Movement (kuantitas negatif karena barang keluar)
            StockMovement.objects.create(
                product=item.product,
                location=purchase_return.return_from_location,
                movement_type='PURCHASE_RETURN',
                quantity=-item.quantity,
                unit_cost=item.unit_price, # Gunakan harga beli saat retur
                reference_number=purchase_return.return_number,
                user=request.user
            )
            total_cost += item.quantity * item.unit_price

        if total_cost > 0:
            journal = JournalEntry.objects.create(
                entry_date=timezone.now().date(),
                entry_type='PURCHASE_RETURN_STOCK',
                description=f"Stock Reversal for PR {purchase_return.return_number}",
                created_by=request.user
            )
            # DEBIT: Akun Kliring Retur Pembelian
            JournalEntryLine.objects.create(journal_entry=journal, account=purchase_return_account, debit_amount=total_cost)
            # KREDIT: Persediaan
            JournalEntryLine.objects.create(journal_entry=journal, account=inventory_account, credit_amount=total_cost)
            
            journal.total_debit = total_cost
            journal.total_credit = total_cost
            journal.status = 'POSTED'
            journal.save()
        # --------------------------------------------

        purchase_return.status = 'SHIPPED'
        purchase_return.items_shipped_by = request.user
        purchase_return.items_shipped_date = timezone.now()
        purchase_return.save()
        return Response(self.get_serializer(purchase_return).data)

class ConsignmentReceiptViewSet(viewsets.ModelViewSet):
    queryset = ConsignmentReceipt.objects.all()
    serializer_class = ConsignmentReceiptSerializer # Buat serializer ini
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def receive(self, request, pk=None):
        receipt = self.get_object()
        if receipt.status != 'DRAFT':
            return Response({'error': 'Only DRAFT receipts can be processed.'}, status=status.HTTP_400_BAD_REQUEST)

        # Buat Stock Movement dengan status kepemilikan 'CONSIGNED'
        for item in receipt.items.all():
            # Ini tidak memicu sinyal post_save, jadi kita update stok secara manual
            stock, _ = Stock.objects.get_or_create(
                product=item.product,
                location=receipt.location,
                ownership_status='CONSIGNED', # <-- KUNCI UTAMA
                defaults={'quantity_on_hand': 0}
            )
            stock.quantity_on_hand += item.quantity
            stock.save()

        receipt.status = 'RECEIVED'
        receipt.save()
        return Response(self.get_serializer(receipt).data)
