from django.db import models
from django.conf import settings
from django.utils import timezone
from common.models import BaseModel, Contact

class Supplier(BaseModel):
    """Enhanced Supplier model with more detailed information"""
    name = models.CharField(max_length=255, db_index=True)
    supplier_id = models.CharField(max_length=50, unique=True, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    full_address = models.CharField(max_length=255, blank=True, null=True)
    contact_person = models.CharField(max_length=255, blank=True, null=True)
    tax_id = models.CharField(max_length=50, blank=True, null=True)
    payment_terms = models.CharField(max_length=100, blank=True, null=True)
    currency = models.CharField(max_length=3, default='IDR')
    notes = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Supplier"
        verbose_name_plural = "Suppliers"
        db_table = "purchasing_suppliers"

    def __str__(self):
        return self.name

class PurchaseOrder(BaseModel):
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("PENDING", "Pending"),
        ("CONFIRMED", "Confirmed"),
        ("RECEIVED", "Received"),
        ("CANCELLED", "Cancelled"),
    ]

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    order_date = models.DateField(auto_now_add=True)
    expected_delivery_date = models.DateField(blank=True, null=True)
    order_number = models.CharField(max_length=50, unique=True, blank=True, null=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    notes = models.TextField(blank=True, null=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_orders_approved"
    )

    class Meta:
        verbose_name = "Purchase Order"
        verbose_name_plural = "Purchase Orders"
        db_table = "purchasing_purchase_orders"
        ordering = ["-order_date", "-created_at"]

    def __str__(self):
        return f"PO {self.order_number} from {self.supplier.name}"

class PurchaseOrderItem(BaseModel):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey('inventory.Product', on_delete=models.PROTECT, related_name='purchase_order_items')
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    line_total = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Purchase Order Item"
        verbose_name_plural = "Purchase Order Items"
        db_table = "purchasing_purchase_order_items"

    def __str__(self):
        return f"{self.product.name} x {self.quantity} in PO {self.purchase_order.order_number}"

class Bill(BaseModel):
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("PENDING", "Pending"),
        ("PAID", "Paid"),
        ("OVERDUE", "Overdue"),
        ("CANCELLED", "Cancelled"),
    ]

    purchase_order = models.ForeignKey(
        PurchaseOrder, 
        on_delete=models.PROTECT, 
        blank=True, 
        null=True,
        related_name="bills" # Tambahkan related_name
    )
    goods_receipt = models.ForeignKey(
        'inventory.GoodsReceipt', # Gunakan string untuk menghindari circular import
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bills"
    )
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    bill_date = models.DateField() 
    due_date = models.DateField()
    bill_number = models.CharField(max_length=50, unique=True, blank=True, null=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING") # Default ke PENDING
    total_amount = models.DecimalField(max_digits=12, decimal_places=2) # Perbesar max_digits
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    balance_due = models.DecimalField(max_digits=12, decimal_places=2) # Akan kita isi otomatis
    notes = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Bill"
        verbose_name_plural = "Bills"
        db_table = "purchasing_bills"
        ordering = ["-bill_date", "-created_at"]

    def __str__(self):
        return f"Bill {self.bill_number} from {self.supplier.name}"

    def save(self, *args, **kwargs):
        # Jika ini adalah Bill baru, atur balance_due
        if not self.pk:
            self.balance_due = self.total_amount

        # Jika nomor bill belum ada, buat secara otomatis
        if not self.bill_number:
            today = timezone.now().date()
            prefix = f"BILL-{today.strftime('%Y%m')}-"
            last_bill = Bill.objects.filter(bill_number__startswith=prefix).order_by('bill_number').last()
            if last_bill:
                last_num = int(last_bill.bill_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            self.bill_number = f"{prefix}{new_num:04d}"

        super().save(*args, **kwargs)

class SupplierPayment(BaseModel):
    PAYMENT_METHODS = [
        ("CASH", "Cash"),
        ("BANK_TRANSFER", "Bank Transfer"),
        ("CREDIT_CARD", "Credit Card"),
        ("OTHER", "Other"),
    ]

    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, related_name="payments")
    payment_date = models.DateField(auto_now_add=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Supplier Payment"
        verbose_name_plural = "Supplier Payments"
        db_table = "purchasing_supplier_payments"
        ordering = ["-payment_date"]

    def __str__(self):
        return f"Payment of {self.amount} for Bill {self.bill.bill_number}"

class PurchaseReturn(BaseModel):
    """Dokumen utama untuk Retur Pembelian (Debit Note)."""
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('APPROVED', 'Approved'),
        ('SHIPPED', 'Shipped'), # Setelah barang dikirim kembali
        ('CANCELLED', 'Cancelled'),
    ]

    return_number = models.CharField(max_length=50, unique=True, blank=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_returns')
    return_date = models.DateField(default=timezone.now)
    
    # Tautkan ke dokumen sumber
    bill = models.ForeignKey(Bill, on_delete=models.SET_NULL, null=True, blank=True, related_name='returns')
    goods_receipt = models.ForeignKey('inventory.GoodsReceipt', on_delete=models.SET_NULL, null=True, blank=True, related_name='returns')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    reason = models.TextField(blank=True, null=True)
    
    # Info pengiriman kembali barang
    items_shipped_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='shipped_purchase_returns')
    items_shipped_date = models.DateTimeField(null=True, blank=True)
    # Lokasi asal barang yang diretur
    return_from_location = models.ForeignKey('inventory.Location', on_delete=models.PROTECT, help_text="Lokasi asal barang retur")

    def save(self, *args, **kwargs):
        if not self.return_number:
            prefix = f"PR-{self.return_date.year}-"
            last_return = PurchaseReturn.objects.filter(return_number__startswith=prefix).order_by('return_number').last()
            if last_return:
                last_num = int(last_return.return_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            self.return_number = f"{prefix}{new_num:05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.return_number

class PurchaseReturnItem(BaseModel):
    """Item-item yang ada di dalam dokumen PurchaseReturn."""
    purchase_return = models.ForeignKey(PurchaseReturn, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('inventory.Product', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=15, decimal_places=2)

    def save(self, *args, **kwargs):
        self.line_total = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

class ConsignmentReceipt(BaseModel):
    """Dokumen untuk mencatat penerimaan barang titipan dari supplier."""
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('RECEIVED', 'Received'),
    ]
    receipt_number = models.CharField(max_length=50, unique=True, blank=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='consignment_receipts')
    receipt_date = models.DateField(default=timezone.now)
    location = models.ForeignKey('inventory.Location', on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    notes = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            prefix = f"CRCV-{self.receipt_date.year}-"
            last_receipt = ConsignmentReceipt.objects.filter(receipt_number__startswith=prefix).order_by('receipt_number').last()
            last_num = int(last_receipt.receipt_number.split('-')[-1]) if last_receipt else 0
            self.receipt_number = f"{prefix}{last_num + 1:05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.receipt_number

class ConsignmentReceiptItem(BaseModel):
    """Item-item dalam penerimaan konsinyasi."""
    receipt = models.ForeignKey(ConsignmentReceipt, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('inventory.Product', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, help_text="Harga beli jika barang ini dikonsumsi/dibeli")

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

