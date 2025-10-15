from rest_framework import serializers
from .models import Supplier, PurchaseOrder, PurchaseOrderItem, Bill, SupplierPayment
from common.serializers import AddressSerializer
from inventory.serializers import ProductSerializer
from inventory.models import Product

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

    class Meta:
        model = PurchaseOrder
        fields = ["id", "supplier", "supplier_name", "order_date", "expected_delivery_date", "order_number", "status", "total_amount", "notes", "items", "created_at", "updated_at"]

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

