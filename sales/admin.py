from django.contrib import admin
from django.utils.html import format_html
from .models import Customer, SalesOrder, SalesOrderItem, Invoice, Payment

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'customer_id', 'email', 'phone', 'city', 'is_active', 'created_at']
    list_filter = ['is_active', 'city', 'state', 'country', 'created_at']
    search_fields = ['name', 'customer_id', 'email', 'phone', 'company_name', 'contact_person']
    readonly_fields = ['customer_id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'customer_id', 'company_name', 'contact_person', 'is_active')
        }),
        ('Contact Information', {
            'fields': ('email', 'phone', 'mobile')
        }),
        ('Address Information', {
            'fields': ('address_line_1', 'address_line_2', 'city', 'state', 'postal_code', 'country')
        }),
        ('Business Information', {
            'fields': ('tax_id', 'credit_limit', 'payment_terms', 'discount_percentage')
        }),
        ('Additional Information', {
            'fields': ('notes',)
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

class SalesOrderItemInline(admin.TabularInline):
    model = SalesOrderItem
    extra = 1
    readonly_fields = ['line_total', 'discount_amount']
    fields = ['product', 'quantity', 'unit_price', 'discount_percentage', 'discount_amount', 'line_total', 'notes']

@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'customer', 'order_date', 'status', 'total_amount_formatted', 'item_count']
    list_filter = ['status', 'order_date', 'created_at']
    search_fields = ['order_number', 'customer__name', 'notes']
    readonly_fields = ['order_number', 'subtotal', 'discount_amount', 'tax_amount', 'total_amount', 'created_at', 'updated_at']
    inlines = [SalesOrderItemInline]
    
    fieldsets = (
        ('Order Information', {
            'fields': ('order_number', 'customer', 'order_date', 'due_date', 'status', 'sales_person')
        }),
        ('Financial Information', {
            'fields': ('subtotal', 'discount_percentage', 'discount_amount', 'tax_percentage', 'tax_amount', 'shipping_cost', 'total_amount')
        }),
        ('Shipping Address', {
            'fields': ('shipping_address_line_1', 'shipping_address_line_2', 'shipping_city', 'shipping_state', 'shipping_postal_code'),
            'classes': ('collapse',)
        }),
        ('Billing Address', {
            'fields': ('billing_address_line_1', 'billing_address_line_2', 'billing_city', 'billing_state', 'billing_postal_code'),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('notes', 'internal_notes'),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def total_amount_formatted(self, obj):
        return f"Rp {obj.total_amount:,.0f}"
    total_amount_formatted.short_description = 'Total Amount'
    
    def item_count(self, obj):
        return obj.items.count()
    item_count.short_description = 'Items'

@admin.register(SalesOrderItem)
class SalesOrderItemAdmin(admin.ModelAdmin):
    list_display = ['sales_order', 'product', 'quantity', 'unit_price_formatted', 'line_total_formatted']
    list_filter = ['sales_order__status', 'created_at']
    search_fields = ['sales_order__order_number', 'product__name', 'product__sku']
    readonly_fields = ['line_total', 'discount_amount']
    
    def unit_price_formatted(self, obj):
        return f"Rp {obj.unit_price:,.0f}"
    unit_price_formatted.short_description = 'Unit Price'
    
    def line_total_formatted(self, obj):
        return f"Rp {obj.line_total:,.0f}"
    line_total_formatted.short_description = 'Line Total'

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'customer', 'invoice_date', 'due_date', 'status', 'total_amount_formatted', 'balance_due_formatted', 'is_overdue_display']
    list_filter = ['status', 'invoice_date', 'due_date', 'created_at']
    search_fields = ['invoice_number', 'customer__name', 'notes']
    readonly_fields = ['invoice_number', 'balance_due', 'amount_paid', 'is_overdue', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Invoice Information', {
            'fields': ('invoice_number', 'sales_order', 'customer', 'invoice_date', 'due_date', 'status', 'payment_terms')
        }),
        ('Financial Information', {
            'fields': ('subtotal', 'discount_amount', 'tax_amount', 'total_amount', 'amount_paid', 'balance_due')
        }),
        ('Additional Information', {
            'fields': ('notes',)
        }),
        ('System Information', {
            'fields': ('is_overdue', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def total_amount_formatted(self, obj):
        return f"Rp {obj.total_amount:,.0f}"
    total_amount_formatted.short_description = 'Total Amount'
    
    def balance_due_formatted(self, obj):
        return f"Rp {obj.balance_due:,.0f}"
    balance_due_formatted.short_description = 'Balance Due'
    
    def is_overdue_display(self, obj):
        if obj.is_overdue:
            return format_html('<span style="color: red;">Yes</span>')
        return format_html('<span style="color: green;">No</span>')
    is_overdue_display.short_description = 'Overdue'

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'customer_name', 'payment_date', 'amount_formatted', 'payment_method', 'reference_number']
    list_filter = ['payment_method', 'payment_date', 'created_at']
    search_fields = ['invoice__invoice_number', 'invoice__customer__name', 'reference_number', 'transaction_id']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Payment Information', {
            'fields': ('invoice', 'payment_date', 'amount', 'payment_method')
        }),
        ('Reference Information', {
            'fields': ('reference_number', 'transaction_id')
        }),
        ('Additional Information', {
            'fields': ('notes',)
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def customer_name(self, obj):
        return obj.invoice.customer.name
    customer_name.short_description = 'Customer'
    
    def amount_formatted(self, obj):
        return f"Rp {obj.amount:,.0f}"
    amount_formatted.short_description = 'Amount'
