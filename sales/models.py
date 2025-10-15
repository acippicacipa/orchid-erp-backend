from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from common.models import BaseModel, Address, Contact
from accounts.models import UserProfile
from inventory.models import Product

class Customer(BaseModel):
    """
    Customer model for managing customer information
    """
    name = models.CharField(max_length=255, db_index=True, help_text="Customer name")
    customer_id = models.CharField(max_length=50, unique=True, blank=True, null=True, help_text="Unique customer ID")
    email = models.EmailField(blank=True, null=True, help_text="Customer email address")
    phone = models.CharField(max_length=20, blank=True, null=True, help_text="Customer phone number")
    mobile = models.CharField(max_length=20, blank=True, null=True, help_text="Customer mobile number")
    
    # Address information
    address_line_1 = models.CharField(max_length=255, blank=True, null=True, help_text="Address line 1")
    address_line_2 = models.CharField(max_length=255, blank=True, null=True, help_text="Address line 2")
    city = models.CharField(max_length=100, blank=True, null=True, help_text="City")
    state = models.CharField(max_length=100, blank=True, null=True, help_text="State/Province")
    postal_code = models.CharField(max_length=20, blank=True, null=True, help_text="Postal code")
    country = models.CharField(max_length=100, default='Indonesia', help_text="Country")
    
    # Business information
    contact_person = models.CharField(max_length=255, blank=True, null=True, help_text="Contact person name")
    company_name = models.CharField(max_length=255, blank=True, null=True, help_text="Company name")
    tax_id = models.CharField(max_length=50, blank=True, null=True, help_text="Tax ID/NPWP")
    
    # Customer settings
    customer_group = models.ForeignKey('CustomerGroup', on_delete=models.SET_NULL, null=True, blank=True, help_text="Customer group for pricing and discounts")
    credit_limit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Credit limit in IDR")
    payment_terms = models.CharField(max_length=100, default='Net 30 days', help_text="Payment terms")
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="Default discount percentage")
    
    # Status and notes
    is_active = models.BooleanField(default=True, help_text="Is customer active")
    notes = models.TextField(blank=True, null=True, help_text="Additional notes")

    class Meta:
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
        db_table = "sales_customers"
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def full_address(self):
        """Return formatted full address"""
        address_parts = [
            self.address_line_1,
            self.address_line_2,
            self.city,
            self.state,
            self.postal_code,
            self.country
        ]
        return ', '.join([part for part in address_parts if part])

    def save(self, *args, **kwargs):
        if not self.customer_id:
            # Auto-generate customer ID
            last_customer = Customer.objects.filter(customer_id__startswith='CUST').order_by('-customer_id').first()
            if last_customer and last_customer.customer_id:
                try:
                    last_number = int(last_customer.customer_id.replace('CUST', ''))
                    self.customer_id = f'CUST{last_number + 1:04d}'
                except:
                    self.customer_id = 'CUST0001'
            else:
                self.customer_id = 'CUST0001'
        super().save(*args, **kwargs)

class SalesOrder(BaseModel):
    """
    Sales Order model with Indonesian Rupiah support
    """
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("PENDING", "Pending"),
        ("CONFIRMED", "Confirmed"),
        ("PROCESSING", "Processing"),
        ("SHIPPED", "Shipped"),
        ("DELIVERED", "Delivered"),
        ("CANCELLED", "Cancelled"),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='sales_orders')
    order_date = models.DateField(auto_now_add=True)
    due_date = models.DateField(blank=True, null=True, help_text="Expected delivery date")
    order_number = models.CharField(max_length=50, unique=True, blank=True, null=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")
    
    # Financial fields in Indonesian Rupiah
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Subtotal in IDR")
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="Discount percentage")
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Discount amount in IDR")
    tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=11.00, help_text="Tax percentage (PPN)")
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Tax amount in IDR")
    shipping_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Shipping cost in IDR")
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Total amount in IDR")
    
    # Address information
    shipping_address_line_1 = models.CharField(max_length=255, blank=True, null=True)
    shipping_address_line_2 = models.CharField(max_length=255, blank=True, null=True)
    shipping_city = models.CharField(max_length=100, blank=True, null=True)
    shipping_state = models.CharField(max_length=100, blank=True, null=True)
    shipping_postal_code = models.CharField(max_length=20, blank=True, null=True)
    
    billing_address_line_1 = models.CharField(max_length=255, blank=True, null=True)
    billing_address_line_2 = models.CharField(max_length=255, blank=True, null=True)
    billing_city = models.CharField(max_length=100, blank=True, null=True)
    billing_state = models.CharField(max_length=100, blank=True, null=True)
    billing_postal_code = models.CharField(max_length=20, blank=True, null=True)
    
    # Additional information
    sales_person = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True, help_text="Sales person")
    notes = models.TextField(blank=True, null=True, help_text="Order notes")
    internal_notes = models.TextField(blank=True, null=True, help_text="Internal notes")

    class Meta:
        verbose_name = "Sales Order"
        verbose_name_plural = "Sales Orders"
        db_table = "sales_orders"
        ordering = ["-order_date", "-created_at"]

    def __str__(self):
        return f"SO-{self.order_number or self.id} - {self.customer.name}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            # Auto-generate order number
            from datetime import datetime
            today = datetime.now()
            prefix = f"SO{today.strftime('%Y%m')}"
            last_order = SalesOrder.objects.filter(order_number__startswith=prefix).order_by('-order_number').first()
            if last_order and last_order.order_number:
                try:
                    last_number = int(last_order.order_number.replace(prefix, ''))
                    self.order_number = f'{prefix}{last_number + 1:04d}'
                except:
                    self.order_number = f'{prefix}0001'
            else:
                self.order_number = f'{prefix}0001'
        super().save(*args, **kwargs)

    def calculate_totals(self):
        """Calculate order totals based on items"""
        items = self.items.all()
        self.subtotal = sum(item.line_total for item in items)
        
        # Calculate discount
        if self.discount_percentage > 0:
            self.discount_amount = (self.subtotal * Decimal(str(self.discount_percentage)) / 100).quantize(Decimal('0.01'))
        else:
            self.discount_amount = Decimal('0.00')
        
        # Calculate tax on (subtotal - discount)
        taxable_amount = self.subtotal - self.discount_amount
        if self.tax_percentage > 0:
            self.tax_amount = (taxable_amount * Decimal(str(self.tax_percentage)) / 100).quantize(Decimal('0.01'))
        else:
            self.tax_amount = Decimal('0.00')
        
        # Calculate total
        self.total_amount = self.subtotal - self.discount_amount + self.tax_amount + self.shipping_cost
        
        self.save()

    @property
    def customer_name(self):
        return self.customer.name if self.customer else ""

    @property
    def item_count(self):
        return self.items.count()

class SalesOrderItem(BaseModel):
    """
    Sales Order Item model with detailed pricing
    """
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    unit_price = models.DecimalField(max_digits=15, decimal_places=2, help_text="Unit price in IDR")
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="Item discount percentage")
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Item discount amount in IDR")
    line_total = models.DecimalField(max_digits=15, decimal_places=2, help_text="Line total in IDR")
    notes = models.TextField(blank=True, null=True, help_text="Item notes")

    class Meta:
        verbose_name = "Sales Order Item"
        verbose_name_plural = "Sales Order Items"
        db_table = "sales_order_items"
        unique_together = ['sales_order', 'product']

    def __str__(self):
        return f"{self.product.name} x {self.quantity} in {self.sales_order.order_number}"

    def save(self, *args, **kwargs):
        # Calculate line total
        subtotal = self.quantity * self.unit_price
        
        # Apply discount
        if self.discount_percentage > 0:
            self.discount_amount = (subtotal * Decimal(str(self.discount_percentage)) / 100).quantize(Decimal('0.01'))
        else:
            self.discount_amount = Decimal('0.00')
        
        self.line_total = subtotal - self.discount_amount
        
        super().save(*args, **kwargs)
        
        # Update sales order totals (disabled for sample data creation)
        # self.sales_order.calculate_totals()

    @property
    def product_name(self):
        return self.product.name if self.product else ""

    @property
    def product_sku(self):
        return self.product.sku if self.product else ""

class Invoice(BaseModel):
    """
    Invoice model with Indonesian Rupiah support
    """
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("SENT", "Sent"),
        ("PARTIAL", "Partially Paid"),
        ("PAID", "Paid"),
        ("OVERDUE", "Overdue"),
        ("CANCELLED", "Cancelled"),
    ]

    sales_order = models.OneToOneField(SalesOrder, on_delete=models.PROTECT, blank=True, null=True, related_name='invoice')
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='invoices')
    invoice_date = models.DateField(auto_now_add=True)
    due_date = models.DateField(help_text="Payment due date")
    invoice_number = models.CharField(max_length=50, unique=True, blank=True, null=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")
    
    # Financial fields in Indonesian Rupiah
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, help_text="Subtotal in IDR")
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Discount amount in IDR")
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Tax amount in IDR")
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, help_text="Total amount in IDR")
    amount_paid = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Amount paid in IDR")
    balance_due = models.DecimalField(max_digits=15, decimal_places=2, help_text="Balance due in IDR")
    
    # Additional information
    payment_terms = models.CharField(max_length=100, default='Net 30 days')
    notes = models.TextField(blank=True, null=True, help_text="Invoice notes")

    class Meta:
        verbose_name = "Invoice"
        verbose_name_plural = "Invoices"
        db_table = "sales_invoices"
        ordering = ["-invoice_date", "-created_at"]

    def __str__(self):
        return f"INV-{self.invoice_number or self.id} - {self.customer.name}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            # Auto-generate invoice number
            from datetime import datetime
            today = datetime.now()
            prefix = f"INV{today.strftime('%Y%m')}"
            last_invoice = Invoice.objects.filter(invoice_number__startswith=prefix).order_by('-invoice_number').first()
            if last_invoice and last_invoice.invoice_number:
                try:
                    last_number = int(last_invoice.invoice_number.replace(prefix, ''))
                    self.invoice_number = f'{prefix}{last_number + 1:04d}'
                except:
                    self.invoice_number = f'{prefix}0001'
            else:
                self.invoice_number = f'{prefix}0001'
        
        # Calculate balance due
        self.balance_due = self.total_amount - self.amount_paid
        
        # Update status based on payment
        if self.amount_paid >= self.total_amount:
            self.status = 'PAID'
        elif self.amount_paid > 0:
            self.status = 'PARTIAL'
        
        super().save(*args, **kwargs)

    @property
    def customer_name(self):
        return self.customer.name if self.customer else ""

    @property
    def is_overdue(self):
        from datetime import date
        return self.due_date < date.today() and self.status not in ['PAID', 'CANCELLED']

class Payment(BaseModel):
    """
    Payment model for invoice payments
    """
    PAYMENT_METHODS = [
        ("CASH", "Cash"),
        ("BANK_TRANSFER", "Bank Transfer"),
        ("CREDIT_CARD", "Credit Card"),
        ("DEBIT_CARD", "Debit Card"),
        ("E_WALLET", "E-Wallet"),
        ("CHECK", "Check"),
        ("OTHER", "Other"),
    ]

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    payment_date = models.DateField(auto_now_add=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2, help_text="Payment amount in IDR")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    reference_number = models.CharField(max_length=100, blank=True, null=True, help_text="Payment reference number")
    transaction_id = models.CharField(max_length=100, blank=True, null=True, help_text="Transaction ID")
    notes = models.TextField(blank=True, null=True, help_text="Payment notes")

    class Meta:
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        db_table = "sales_payments"
        ordering = ["-payment_date"]

    def __str__(self):
        return f"Payment {self.amount} for {self.invoice.invoice_number}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        
        # Update invoice amount paid
        total_payments = self.invoice.payments.aggregate(
            total=models.Sum('amount')
        )['total'] or 0
        
        self.invoice.amount_paid = total_payments
        self.invoice.save()


class DownPayment(BaseModel):
    """
    Down Payment model for customer advance payments
    """
    PAYMENT_METHODS = [
        ("CASH", "Cash"),
        ("BANK_TRANSFER", "Bank Transfer"),
        ("CREDIT_CARD", "Credit Card"),
        ("DEBIT_CARD", "Debit Card"),
        ("E_WALLET", "E-Wallet"),
        ("CHECK", "Check"),
        ("OTHER", "Other"),
    ]

    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("USED", "Used"),
        ("REFUNDED", "Refunded"),
        ("EXPIRED", "Expired"),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='down_payments')
    down_payment_number = models.CharField(max_length=50, unique=True, blank=True, null=True, db_index=True)
    payment_date = models.DateField(auto_now_add=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2, help_text="Down payment amount in IDR")
    remaining_amount = models.DecimalField(max_digits=15, decimal_places=2, help_text="Remaining amount available for use")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    reference_number = models.CharField(max_length=100, blank=True, null=True, help_text="Payment reference number")
    transaction_id = models.CharField(max_length=100, blank=True, null=True, help_text="Transaction ID")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ACTIVE")
    expiry_date = models.DateField(blank=True, null=True, help_text="Expiry date for down payment")
    notes = models.TextField(blank=True, null=True, help_text="Down payment notes")

    class Meta:
        verbose_name = "Down Payment"
        verbose_name_plural = "Down Payments"
        db_table = "sales_down_payments"
        ordering = ["-payment_date"]

    def __str__(self):
        return f"DP {self.down_payment_number} - {self.customer.name} - Rp {self.remaining_amount:,.0f}"

    @property
    def used_amount(self):
        """Calculate used amount from down payment"""
        return self.amount - self.remaining_amount

    @property
    def is_available(self):
        """Check if down payment is available for use"""
        return self.status == "ACTIVE" and self.remaining_amount > 0

    def save(self, *args, **kwargs):
        if not self.down_payment_number:
            # Auto-generate down payment number
            last_dp = DownPayment.objects.filter(down_payment_number__startswith='DP').order_by('-down_payment_number').first()
            if last_dp and last_dp.down_payment_number:
                try:
                    last_number = int(last_dp.down_payment_number.replace('DP', ''))
                    self.down_payment_number = f'DP{last_number + 1:06d}'
                except:
                    self.down_payment_number = 'DP000001'
            else:
                self.down_payment_number = 'DP000001'
        
        # Set remaining amount to full amount if not set
        if not self.remaining_amount:
            self.remaining_amount = self.amount
            
        super().save(*args, **kwargs)


class DownPaymentUsage(BaseModel):
    """
    Track usage of down payments in invoices/sales orders
    """
    down_payment = models.ForeignKey(DownPayment, on_delete=models.PROTECT, related_name='usages')
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name='down_payment_usages', blank=True, null=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='down_payment_usages', blank=True, null=True)
    amount_used = models.DecimalField(max_digits=15, decimal_places=2, help_text="Amount used from down payment")
    usage_date = models.DateField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True, help_text="Usage notes")

    class Meta:
        verbose_name = "Down Payment Usage"
        verbose_name_plural = "Down Payment Usages"
        db_table = "sales_down_payment_usages"
        ordering = ["-usage_date"]

    def __str__(self):
        target = self.invoice or self.sales_order
        return f"DP Usage {self.amount_used} for {target}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        
        # Update down payment remaining amount
        total_used = self.down_payment.usages.aggregate(
            total=models.Sum('amount_used')
        )['total'] or 0
        
        self.down_payment.remaining_amount = self.down_payment.amount - total_used
        
        # Update status if fully used
        if self.down_payment.remaining_amount <= 0:
            self.down_payment.status = "USED"
        
        self.down_payment.save()


# Import discount models
from .discount_models import (
    CustomerGroup, ProductDiscount, QuantityDiscount, 
    WholesalerDiscount, DiscountCalculationService
)
