from django.contrib import admin
from .models import Supplier, PurchaseOrder, PurchaseOrderItem, Bill, SupplierPayment

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'supplier_id', 'email', 'phone', 'contact_person', 'payment_terms', 'created_at']
    list_filter = ['currency', 'created_at', 'updated_at']
    search_fields = ['name', 'supplier_id', 'email', 'contact_person']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'supplier_id', 'email', 'phone')
        }),
        ('Contact Details', {
            'fields': ('contact_person', 'address')
        }),
        ('Business Information', {
            'fields': ('tax_id', 'payment_terms', 'currency')
        }),
        ('Additional Information', {
            'fields': ('notes',)
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 1
    fields = ['product', 'quantity', 'unit_price', 'line_total']
    readonly_fields = ['line_total']

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'supplier', 'order_date', 'status', 'total_amount', 'expected_delivery_date']
    list_filter = ['status', 'order_date', 'expected_delivery_date', 'created_at']
    search_fields = ['order_number', 'supplier__name']
    readonly_fields = ['created_at', 'updated_at', 'total_amount']
    inlines = [PurchaseOrderItemInline]
    
    fieldsets = (
        ('Order Information', {
            'fields': ('supplier', 'order_number', 'status')
        }),
        ('Dates', {
            'fields': ('order_date', 'expected_delivery_date')
        }),
        ('Financial', {
            'fields': ('total_amount',)
        }),
        ('Additional Information', {
            'fields': ('notes',)
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Recalculate total amount
        total = sum(item.line_total for item in obj.items.all())
        if obj.total_amount != total:
            obj.total_amount = total
            obj.save()

@admin.register(PurchaseOrderItem)
class PurchaseOrderItemAdmin(admin.ModelAdmin):
    list_display = ['purchase_order', 'product', 'quantity', 'unit_price', 'line_total']
    list_filter = ['purchase_order__status', 'product__main_category', 'created_at']
    search_fields = ['purchase_order__order_number', 'product__name']
    readonly_fields = ['created_at', 'updated_at']

class SupplierPaymentInline(admin.TabularInline):
    model = SupplierPayment
    extra = 0
    fields = ['payment_date', 'amount', 'payment_method', 'transaction_id']
    readonly_fields = ['payment_date']

@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ['bill_number', 'supplier', 'bill_date', 'due_date', 'status', 'total_amount', 'balance_due']
    list_filter = ['status', 'bill_date', 'due_date', 'created_at']
    search_fields = ['bill_number', 'supplier__name', 'purchase_order__order_number']
    readonly_fields = ['created_at', 'updated_at', 'balance_due']
    inlines = [SupplierPaymentInline]
    
    fieldsets = (
        ('Bill Information', {
            'fields': ('supplier', 'purchase_order', 'bill_number', 'status')
        }),
        ('Dates', {
            'fields': ('bill_date', 'due_date')
        }),
        ('Financial', {
            'fields': ('total_amount', 'amount_paid', 'balance_due')
        }),
        ('Additional Information', {
            'fields': ('notes',)
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Recalculate balance due
        obj.balance_due = obj.total_amount - obj.amount_paid
        obj.save()

@admin.register(SupplierPayment)
class SupplierPaymentAdmin(admin.ModelAdmin):
    list_display = ['bill', 'payment_date', 'amount', 'payment_method', 'transaction_id']
    list_filter = ['payment_method', 'payment_date', 'created_at']
    search_fields = ['bill__bill_number', 'bill__supplier__name', 'transaction_id']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Payment Information', {
            'fields': ('bill', 'amount', 'payment_method')
        }),
        ('Transaction Details', {
            'fields': ('payment_date', 'transaction_id')
        }),
        ('Additional Information', {
            'fields': ('notes',)
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
