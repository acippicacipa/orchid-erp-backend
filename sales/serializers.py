from rest_framework import serializers
from decimal import Decimal
from django.db.models import Sum
from .models import Customer, CustomerGroup, SalesOrder, SalesOrderItem, Invoice, Payment, DownPayment, DownPaymentUsage
from inventory.models import Product, Stock

class CustomerGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerGroup
        fields = ['id', 'name', 'description', 'discount_percentage']

class CustomerSerializer(serializers.ModelSerializer):
    full_address = serializers.ReadOnlyField()
    customer_group_name = serializers.CharField(source='customer_group.name', read_only=True, allow_null=True)
    group_discount_percentage = serializers.DecimalField(
        source='customer_group.discount_percentage', 
        read_only=True, 
        max_digits=5, 
        decimal_places=2,
        allow_null=True
    )

    class Meta:
        model = Customer
        # Tambahkan 'customer_group_name' ke fields
        fields = [
            'id', 'name', 'customer_id', 'email', 'phone', 'mobile', 
            'address_line_1', 'address_line_2', 'city', 'state', 'postal_code', 'country',
            'contact_person', 'company_name', 'tax_id', 
            'customer_group', 'customer_group_name', 'group_discount_percentage',
            'payment_type','credit_limit', 'payment_terms',
            'is_active', 'notes', 'full_address',
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')

class ProductSearchSerializer(serializers.ModelSerializer):
    """Serializer for product search in sales orders"""
    category_path = serializers.CharField(read_only=True)
    stock_quantity = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        # Sesuaikan fields dengan yang dibutuhkan frontend
        fields = [
            'id', 
            'name',
            'color',
            'full_name',  
            'sku', 
            'selling_price', # Frontend butuh ini
            'category_path', # Ganti dari category_name
            'stock_quantity',
            'is_sellable', # Tambahkan ini untuk filtering di frontend jika perlu
            'unit_of_measure' # Ganti dari 'unit'
        ]

    def get_stock_quantity(self, obj):
        # Ambil total stok yang bisa dijual dari semua lokasi
        # Ini mungkin perlu disesuaikan jika Anda ingin stok dari lokasi tertentu
        total_sellable = Stock.objects.filter(product=obj).aggregate(
            total=Sum('quantity_sellable')
        )['total'] or 0
        return total_sellable

class SalesOrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField()
    product_sku = serializers.ReadOnlyField()
    product_details = ProductSearchSerializer(source='product', read_only=True)
    
    class Meta:
        model = SalesOrderItem
        fields = [
            'id', 'product', 'product_name', 'product_sku', 'product_details',
            'quantity', 'unit_price', 'discount_percentage', 'discount_amount',
            'line_total', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ('line_total', 'discount_amount', 'created_at', 'updated_at')

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0.")
        return value

    def validate_unit_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Unit price cannot be negative.")
        return value

    def validate_discount_percentage(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Discount percentage must be between 0 and 100.")
        return value

class SalesOrderSerializer(serializers.ModelSerializer):
    items = SalesOrderItemSerializer(many=True, required=False)
    customer_name = serializers.ReadOnlyField()
    item_count = serializers.ReadOnlyField()
    customer_details = CustomerSerializer(source='customer', read_only=True)
    
    # Formatted currency fields for display
    subtotal_formatted = serializers.SerializerMethodField()
    discount_amount_formatted = serializers.SerializerMethodField()
    tax_amount_formatted = serializers.SerializerMethodField()
    total_amount_formatted = serializers.SerializerMethodField()
    
    class Meta:
        model = SalesOrder
        fields = [
            'id', 'customer', 'customer_name', 'customer_details', 'order_date', 'due_date',
            'order_number', 'status', 'subtotal', 'subtotal_formatted',
            'discount_percentage', 'discount_amount', 'discount_amount_formatted',
            'tax_percentage', 'tax_amount', 'tax_amount_formatted',
            'shipping_cost', 'total_amount', 'total_amount_formatted',
            'shipping_address_line_1', 'shipping_address_line_2', 'shipping_city',
            'shipping_state', 'shipping_postal_code',
            'billing_address_line_1', 'billing_address_line_2', 'billing_city',
            'billing_state', 'billing_postal_code',
            'sales_person', 'notes', 'internal_notes', 'items', 'item_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = (
            'order_number', 'subtotal', 'discount_amount', 'tax_amount', 'total_amount',
            'created_at', 'updated_at'
        )

    def get_subtotal_formatted(self, obj):
        return f"Rp {obj.subtotal:,.0f}"

    def get_discount_amount_formatted(self, obj):
        return f"Rp {obj.discount_amount:,.0f}"

    def get_tax_amount_formatted(self, obj):
        return f"Rp {obj.tax_amount:,.0f}"

    def get_total_amount_formatted(self, obj):
        return f"Rp {obj.total_amount:,.0f}"

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        sales_order = SalesOrder.objects.create(**validated_data)
        
        for item_data in items_data:
            SalesOrderItem.objects.create(sales_order=sales_order, **item_data)
        
        sales_order.calculate_totals()
        return sales_order

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        
        # Update sales order fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update items if provided
        if items_data is not None:
            # Delete existing items
            instance.items.all().delete()
            
            # Create new items
            for item_data in items_data:
                SalesOrderItem.objects.create(sales_order=instance, **item_data)
        
        instance.calculate_totals()
        return instance

    def validate_discount_percentage(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Discount percentage must be between 0 and 100.")
        return value

    def validate_tax_percentage(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Tax percentage must be between 0 and 100.")
        return value

class InvoiceSerializer(serializers.ModelSerializer):
    customer_name = serializers.ReadOnlyField()
    customer_details = CustomerSerializer(source='customer', read_only=True)
    sales_order_details = SalesOrderSerializer(source='sales_order', read_only=True)
    is_overdue = serializers.ReadOnlyField()
    
    # Formatted currency fields for display
    subtotal_formatted = serializers.SerializerMethodField()
    discount_amount_formatted = serializers.SerializerMethodField()
    tax_amount_formatted = serializers.SerializerMethodField()
    total_amount_formatted = serializers.SerializerMethodField()
    amount_paid_formatted = serializers.SerializerMethodField()
    balance_due_formatted = serializers.SerializerMethodField()
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'sales_order', 'sales_order_details', 'customer', 'customer_name', 'customer_details',
            'invoice_date', 'due_date', 'invoice_number', 'status',
            'subtotal', 'subtotal_formatted', 'discount_amount', 'discount_amount_formatted',
            'tax_amount', 'tax_amount_formatted', 'total_amount', 'total_amount_formatted',
            'amount_paid', 'amount_paid_formatted', 'balance_due', 'balance_due_formatted',
            'payment_terms', 'notes', 'is_overdue', 'created_at', 'updated_at'
        ]
        read_only_fields = (
            'invoice_number', 'balance_due', 'amount_paid', 'created_at', 'updated_at'
        )

    def get_subtotal_formatted(self, obj):
        return f"Rp {obj.subtotal:,.0f}"

    def get_discount_amount_formatted(self, obj):
        return f"Rp {obj.discount_amount:,.0f}"

    def get_tax_amount_formatted(self, obj):
        return f"Rp {obj.tax_amount:,.0f}"

    def get_total_amount_formatted(self, obj):
        return f"Rp {obj.total_amount:,.0f}"

    def get_amount_paid_formatted(self, obj):
        return f"Rp {obj.amount_paid:,.0f}"

    def get_balance_due_formatted(self, obj):
        return f"Rp {obj.balance_due:,.0f}"

    def create(self, validated_data):
        # If creating from sales order, copy financial data
        sales_order = validated_data.get('sales_order')
        if sales_order:
            validated_data.update({
                'subtotal': sales_order.subtotal,
                'discount_amount': sales_order.discount_amount,
                'tax_amount': sales_order.tax_amount,
                'total_amount': sales_order.total_amount,
            })
        
        return super().create(validated_data)

class PaymentSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)
    customer_name = serializers.CharField(source='invoice.customer.name', read_only=True)
    amount_formatted = serializers.SerializerMethodField()
    
    class Meta:
        model = Payment
        fields = [
            'id', 'invoice', 'invoice_number', 'customer_name', 'payment_date',
            'amount', 'amount_formatted', 'payment_method', 'reference_number',
            'transaction_id', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ('created_at', 'updated_at')

    def get_amount_formatted(self, obj):
        return f"Rp {obj.amount:,.0f}"

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Payment amount must be greater than 0.")
        return value

# Specialized serializers for different use cases
class SalesOrderListSerializer(serializers.ModelSerializer):
    """Simplified serializer for sales order lists"""
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    item_count = serializers.IntegerField(source='items.count', read_only=True)
    total_amount_formatted = serializers.SerializerMethodField()
    order_date = serializers.DateField(format="%d/%m/%Y")
    due_date = serializers.DateField(format="%d/%m/%Y")
    
    class Meta:
        model = SalesOrder
        fields = [
            'id', 'order_number', 'customer_name', 'order_date', 'due_date', 'status',
            'total_amount', 'total_amount_formatted', 'item_count'
        ]

    def get_total_amount_formatted(self, obj):
        return f"Rp {obj.total_amount:,.0f}"

class CustomerListSerializer(serializers.ModelSerializer):
    customer_group_name = serializers.CharField(source='customer_group.name', read_only=True, allow_null=True)
    """Simplified serializer for customer lists"""
    class Meta:
        model = Customer
        fields = [
            'id', 
            'name', 
            'customer_id', 
            'email', 
            'phone', 
            'city', 
            'is_active',
            'payment_type',
            'customer_group', # ID dari grup
            'customer_group_name' # Nama dari grup
        ]

class InvoiceListSerializer(serializers.ModelSerializer):
    """Simplified serializer for invoice lists"""
    customer_name = serializers.ReadOnlyField()
    total_amount_formatted = serializers.SerializerMethodField()
    balance_due_formatted = serializers.SerializerMethodField()
    is_overdue = serializers.ReadOnlyField()
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'customer_name', 'invoice_date', 'due_date',
            'status', 'total_amount', 'total_amount_formatted',
            'balance_due', 'balance_due_formatted', 'is_overdue'
        ]

    def get_total_amount_formatted(self, obj):
        return f"Rp {obj.total_amount:,.0f}"

    def get_balance_due_formatted(self, obj):
        return f"Rp {obj.balance_due:,.0f}"




class DownPaymentSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    used_amount = serializers.ReadOnlyField()
    is_available = serializers.ReadOnlyField()
    
    class Meta:
        model = DownPayment
        fields = [
            'id', 'customer', 'customer_name', 'down_payment_number', 'payment_date',
            'amount', 'remaining_amount', 'used_amount', 'payment_method',
            'reference_number', 'transaction_id', 'status', 'expiry_date',
            'notes', 'is_available', 'created_at', 'updated_at'
        ]
        read_only_fields = ('down_payment_number', 'used_amount', 'is_available', 'created_at', 'updated_at')

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Down payment amount must be greater than 0.")
        return value

    def validate_expiry_date(self, value):
        if value and value <= timezone.now().date():
            raise serializers.ValidationError("Expiry date must be in the future.")
        return value


class DownPaymentUsageSerializer(serializers.ModelSerializer):
    down_payment_number = serializers.CharField(source='down_payment.down_payment_number', read_only=True)
    customer_name = serializers.CharField(source='down_payment.customer.name', read_only=True)
    
    class Meta:
        model = DownPaymentUsage
        fields = [
            'id', 'down_payment', 'down_payment_number', 'customer_name',
            'sales_order', 'invoice', 'amount_used', 'usage_date', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ('usage_date', 'created_at', 'updated_at')

    def validate_amount_used(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount used must be greater than 0.")
        return value

    def validate(self, data):
        down_payment = data.get('down_payment')
        amount_used = data.get('amount_used')
        
        if down_payment and amount_used:
            if amount_used > down_payment.remaining_amount:
                raise serializers.ValidationError(
                    f"Amount used ({amount_used}) cannot exceed remaining amount ({down_payment.remaining_amount})"
                )
            
            if not down_payment.is_available:
                raise serializers.ValidationError("Down payment is not available for use.")
        
        return data


class CustomerDownPaymentSummarySerializer(serializers.ModelSerializer):
    """Serializer for customer with down payment summary"""
    total_down_payments = serializers.SerializerMethodField()
    available_down_payments = serializers.SerializerMethodField()
    total_available_amount = serializers.SerializerMethodField()
    
    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'customer_id', 'email', 'phone',
            'total_down_payments', 'available_down_payments', 'total_available_amount'
        ]
    
    def get_total_down_payments(self, obj):
        return obj.down_payments.count()
    
    def get_available_down_payments(self, obj):
        return obj.down_payments.filter(status='ACTIVE', remaining_amount__gt=0).count()
    
    def get_total_available_amount(self, obj):
        total = obj.down_payments.filter(status='ACTIVE').aggregate(
            total=models.Sum('remaining_amount')
        )['total'] or 0
        return total

from django.utils import timezone
from django.db import models
