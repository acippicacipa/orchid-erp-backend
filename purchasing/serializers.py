from rest_framework import serializers
from .models import (
    Supplier, PurchaseOrder, PurchaseOrderItem, Bill, SupplierPayment, PurchaseReturn, PurchaseReturnItem,
    ConsignmentReceipt, ConsignmentReceiptItem
)
from common.serializers import AddressSerializer
from inventory.serializers import ProductSerializer
from inventory.models import Product
from django.db import transaction

class SupplierSerializer(serializers.ModelSerializer):
    address = AddressSerializer(required=False)

    class Meta:
        model = Supplier
        fields = ["id", "name", "supplier_id", "email", "phone", "address", "contact_person", "tax_id", "payment_terms", "currency", "notes", "created_at", "updated_at"]

class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), source='product', write_only=True)

    class Meta:
        model = PurchaseOrderItem
        fields = ["id", "product", "product_id", "quantity", "unit_price", "line_total"]

class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    supplier_email = serializers.CharField(source='supplier.email', read_only=True)
    supplier_phone = serializers.CharField(source='supplier.phone', read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = ["id", "supplier", "supplier_name", "supplier_phone", "supplier_email", "order_date", "expected_delivery_date", "order_number", "status", "total_amount", "notes", "items", "created_at", "updated_at"]

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        purchase_order = PurchaseOrder.objects.create(**validated_data)
        for item_data in items_data:
            PurchaseOrderItem.objects.create(purchase_order=purchase_order, **item_data)
        return purchase_order

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        
        instance = super().update(instance, validated_data)

        if items_data is not None:
            instance.items.all().delete() # Clear existing items
            for item_data in items_data:
                PurchaseOrderItem.objects.create(purchase_order=instance, **item_data)
        
        return instance

class BillSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    purchase_order_number = serializers.CharField(source='purchase_order.order_number', read_only=True)

    class Meta:
        model = Bill
        fields = ["id", "purchase_order", "purchase_order_number", "supplier", "supplier_name", "bill_date", "due_date", "bill_number", "status", "total_amount", "amount_paid", "balance_due", "notes", "created_at", "updated_at"]
        read_only_fields = ['balance_due'] 

class SupplierPaymentSerializer(serializers.ModelSerializer):
    bill_number = serializers.CharField(source='bill.bill_number', read_only=True)

    class Meta:
        model = SupplierPayment
        fields = ["id", "bill", "bill_number", "payment_date", "amount", "payment_method", "transaction_id", "notes", "created_at", "updated_at"]




class SupplierListSerializer(serializers.ModelSerializer):
    """Simplified serializer for supplier lists"""
    class Meta:
        model = Supplier
        fields = ["id", "name", "supplier_id", "email", "phone", "contact_person", "payment_terms", "currency"]

class PurchaseReturnItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)

    class Meta:
        model = PurchaseReturnItem
        fields = ['id', 'product', 'product_name', 'product_sku', 'quantity', 'unit_price', 'line_total']

class PurchaseReturnSerializer(serializers.ModelSerializer):
    items = PurchaseReturnItemSerializer(many=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    bill_number = serializers.CharField(source='bill.bill_number', read_only=True, allow_null=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    items_shipped_by_name = serializers.CharField(source='items_shipped_by.username', read_only=True)
    return_from_location_name = serializers.CharField(source='return_from_location.name', read_only=True)

    class Meta:
        model = PurchaseReturn
        fields = [
            'id', 'return_number', 'supplier', 'supplier_name', 'return_date', 
            'bill', 'bill_number', 'goods_receipt', 'status', 'total_amount', 
            'reason', 'items_shipped_by_name', 'items_shipped_date', 
            'return_from_location', 'return_from_location_name', 'created_by_name', 'items'
        ]
        read_only_fields = ['return_number', 'total_amount']

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        validated_data['created_by'] = self.context['request'].user
        
        purchase_return = PurchaseReturn.objects.create(**validated_data)
        
        total_amount = sum(item['quantity'] * item['unit_price'] for item in items_data)
        
        for item_data in items_data:
            PurchaseReturnItem.objects.create(purchase_return=purchase_return, **item_data)
        
        purchase_return.total_amount = total_amount
        purchase_return.save()
        
        return purchase_return

class ConsignmentReceiptItemSerializer(serializers.ModelSerializer):
    """
    Serializer untuk item-item di dalam ConsignmentReceipt.
    """
    # Read-only fields untuk menampilkan informasi produk di frontend
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)

    class Meta:
        model = ConsignmentReceiptItem
        fields = [
            'id', 
            'product',       # ID produk untuk write operations (saat membuat)
            'product_name',  # Untuk display di frontend (read-only)
            'product_sku',   # Untuk display di frontend (read-only)
            'quantity', 
            'unit_price'     # Harga beli jika barang ini nanti dikonsumsi
        ]
        # Pastikan 'product' bisa ditulis (writeable)
        extra_kwargs = {
            'product': {'write_only': False} 
        }


class ConsignmentReceiptSerializer(serializers.ModelSerializer):
    """
    Serializer utama untuk ConsignmentReceipt.
    Menangani nested creation untuk item-itemnya.
    """
    # Nested serializer untuk menampilkan dan membuat item
    items = ConsignmentReceiptItemSerializer(many=True)

    # Read-only fields untuk menampilkan informasi relasi di frontend
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = ConsignmentReceipt
        fields = [
            'id', 'receipt_number', 'supplier', 'supplier_name', 'receipt_date',
            'location', 'location_name', 'status', 'notes', 'created_by_name',
            'created_at', 'items'
        ]
        read_only_fields = ['receipt_number', 'created_by_name', 'status']

    @transaction.atomic
    def create(self, validated_data):
        """
        Override metode create untuk menangani pembuatan nested items.
        """
        # 1. Ambil data item dari data yang sudah divalidasi
        items_data = validated_data.pop('items')
        
        # 2. Atur 'created_by' dari user yang sedang login (dari konteks request)
        validated_data['created_by'] = self.context['request'].user
        
        # 3. Buat objek ConsignmentReceipt utama
        receipt = ConsignmentReceipt.objects.create(**validated_data)
        
        # 4. Loop melalui data item dan buat objek ConsignmentReceiptItem
        for item_data in items_data:
            ConsignmentReceiptItem.objects.create(receipt=receipt, **item_data)
        
        # 5. Kembalikan objek receipt yang baru dibuat
        return receipt

    def update(self, instance, validated_data):
        """
        Override metode update (opsional, tapi praktik yang baik).
        Ini menangani pembaruan receipt dan item-itemnya.
        """
        items_data = validated_data.pop('items', None)
        
        # Update field-field di instance utama (ConsignmentReceipt)
        instance = super().update(instance, validated_data)

        # Jika ada data 'items' dalam request, update item-itemnya
        if items_data is not None:
            # Hapus item lama
            instance.items.all().delete()
            # Buat item baru
            for item_data in items_data:
                ConsignmentReceiptItem.objects.create(receipt=instance, **item_data)
        
        return instance

