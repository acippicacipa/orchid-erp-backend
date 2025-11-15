from django.db import models
from django.conf import settings
from common.models import BaseModel, Address, Contact

class Supplier(BaseModel):
    """Enhanced Supplier model with more detailed information"""
    name = models.CharField(max_length=255, db_index=True)
    supplier_id = models.CharField(max_length=50, unique=True, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True)
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

    purchase_order = models.OneToOneField(PurchaseOrder, on_delete=models.PROTECT, blank=True, null=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    bill_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()
    bill_number = models.CharField(max_length=50, unique=True, blank=True, null=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    balance_due = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Bill"
        verbose_name_plural = "Bills"
        db_table = "purchasing_bills"
        ordering = ["-bill_date", "-created_at"]

    def __str__(self):
        return f"Bill {self.bill_number} from {self.supplier.name}"

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

