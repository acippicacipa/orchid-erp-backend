from rest_framework import serializers
from .models import (
    MainCategory, SubCategory, Category, Location, Product, Stock, 
    BillOfMaterials, BOMItem, AssemblyOrder, AssemblyOrderItem
)

class MainCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MainCategory
        fields = ['id', 'name', 'description', 'is_active', 'created_at', 'updated_at']

class SubCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SubCategory
        fields = ['id', 'name', 'description', 'is_active', 'created_at', 'updated_at']

class CategorySerializer(serializers.ModelSerializer):
    main_category_name = serializers.CharField(source='main_category.name', read_only=True)
    sub_category_name = serializers.CharField(source='sub_category.name', read_only=True)
    full_path = serializers.CharField(read_only=True)

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'main_category', 'sub_category', 
            'main_category_name', 'sub_category_name', 'full_path',
            'description', 'is_active', 'created_at', 'updated_at'
        ]

class LocationSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = Location
        fields = [
            'id', 'name', 'location_type', 'code', 'address', 'contact_person',
            'phone', 'email', 'is_active', 'is_sellable_location', 
            'is_purchasable_location', 'is_manufacturing_location',
            'storage_capacity', 'current_utilization', 'notes', 'display_name',
            'created_at', 'updated_at'
        ]

class ProductSerializer(serializers.ModelSerializer):
    main_category_name = serializers.CharField(source='main_category.name', read_only=True)
    sub_category_name = serializers.CharField(source='sub_category.name', read_only=True)
    category_path = serializers.CharField(read_only=True)
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'sku', 'description', 'main_category', 'sub_category',
            'main_category_name', 'sub_category_name', 'category_path', 'full_name',
            'color', 'size', 'brand', 'model', 'cost_price', 'selling_price',
            'unit_of_measure', 'weight', 'dimensions', 'is_active', 'is_sellable',
            'is_purchasable', 'is_manufactured', 'minimum_stock_level',
            'maximum_stock_level', 'reorder_point', 'barcode', 'supplier_code',
            'notes', 'created_at', 'updated_at'
        ]

class StockSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)

    class Meta:
        model = Stock
        fields = [
            'id', 'product', 'location', 'product_name', 'product_sku', 'location_name',
            'quantity_on_hand', 'quantity_sellable', 'quantity_non_sellable',
            'quantity_reserved', 'quantity_allocated', 'average_cost', 'last_cost',
            'last_received_date', 'last_sold_date', 'last_counted_date',
            'bin_location', 'lot_number', 'expiry_date', 'notes',
            'created_at', 'updated_at'
        ]

class BOMItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = BOMItem
        # Tentukan field yang akan diterima dari frontend saat membuat/mengedit BOM
        fields = ['id', 'component', 'quantity', 'notes']
        # 'id' dibuat read_only agar tidak bisa diubah langsung oleh frontend saat update
        read_only_fields = ['id']

class BillOfMaterialsSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    
    bom_items = BOMItemSerializer(many=True)

    class Meta:
        model = BillOfMaterials
        fields = [
            'id', 'product', 'product_name', 'product_sku', 'bom_number',
            'version', 'is_default', 'bom_items', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['bom_number', 'product_name', 'product_sku']

    # Override 'to_representation' untuk menampilkan detail saat membaca
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        # Di sini kita bisa memperkaya data 'bom_items' untuk tampilan
        class BOMItemDetailSerializer(serializers.ModelSerializer):
            component_name = serializers.CharField(source='component.name', read_only=True)
            component_sku = serializers.CharField(source='component.sku', read_only=True)
            class Meta:
                model = BOMItem
                fields = ['id', 'component', 'component_name', 'component_sku', 'quantity', 'notes']
        
        representation['bom_items'] = BOMItemDetailSerializer(instance.bom_items.all(), many=True).data
        return representation

    def create(self, validated_data):
        items_data = validated_data.pop('bom_items')
        bom = BillOfMaterials.objects.create(**validated_data)
        for item_data in items_data:
            BOMItem.objects.create(bom=bom, **item_data)
        return bom

    def update(self, instance, validated_data):
        items_data = validated_data.pop('bom_items', None)
        instance = super().update(instance, validated_data)
        if items_data is not None:
            instance.bom_items.all().delete()
            for item_data in items_data:
                BOMItem.objects.create(bom=instance, **item_data)
        return instance

class AssemblyOrderItemSerializer(serializers.ModelSerializer):
    component_name = serializers.CharField(source='component.name', read_only=True)
    component_sku = serializers.CharField(source='component.sku', read_only=True)

    class Meta:
        model = AssemblyOrderItem
        fields = [
            'id', 'component', 'component_name', 'component_sku',
            'quantity', 'created_at', 'updated_at'
        ]

class AssemblyOrderSerializer(serializers.ModelSerializer):
    bom_number = serializers.CharField(source='bom.bom_number', read_only=True, allow_null=True)
    product_name = serializers.CharField(source='bom.product.name', read_only=True, allow_null=True)
    items = AssemblyOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = AssemblyOrder
        fields = [
            'id', 'bom', 'bom_number', 'product_name', 'quantity',
            'order_date', 'notes', 'items', 'created_at', 'updated_at'
        ]

# Import additional models for goods receipt
from .models import GoodsReceipt, GoodsReceiptItem, StockMovement
from purchasing.models import PurchaseOrder, PurchaseOrderItem

class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    user_name = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            'id', 'product', 'location', 'product_name', 'product_sku', 'location_name',
            'movement_type', 'quantity', 'unit_cost', 'reference_number', 'reference_type',
            'notes', 'user', 'user_name', 'movement_date', 'created_at', 'updated_at'
        ]

# Goods Receipt Serializers
class GoodsReceiptItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    
    class Meta:
        model = GoodsReceiptItem
        fields = [
            'id', 'purchase_order_item', 'product', 'product_name', 'product_sku',
            'quantity_ordered', 'quantity_received', 'unit_price', 'batch_number', 'expiry_date', 'notes',
            'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'product': {'required': True}
        }

class GoodsReceiptSerializer(serializers.ModelSerializer):
    items = GoodsReceiptItemSerializer(many=True, read_only=True)
    purchase_order_number = serializers.CharField(source='purchase_order.order_number', read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True, allow_null=True)
    received_by_name = serializers.CharField(source='received_by.username', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True, allow_null=True)
    
    class Meta:
        model = GoodsReceipt
        fields = [
            'id', 'receipt_number', 'purchase_order', 'purchase_order_number',
            'supplier', # <-- Tambahkan ID supplier
            'supplier_name', # <-- Nama supplier akan berfungsi untuk kedua mode
            'receipt_date', 'received_by', 'received_by_name',
            'status', 'notes', 'location', 'location_name', 
            'items', 'created_at', 'updated_at'
        ]

class CreateGoodsReceiptSerializer(serializers.ModelSerializer):
    items = GoodsReceiptItemSerializer(many=True)
    
    class Meta:
        model = GoodsReceipt
        fields = [
            'purchase_order',
            'supplier', 
            'location',
            'received_by', 
            'notes', 
            'items'
        ]
        extra_kwargs = {
            'purchase_order': {'required': False, 'allow_null': True},
            'supplier': {'required': False, 'allow_null': True}, # <-- Tambahkan ini
            'location': {'required': True},
            'received_by': {'write_only': True}
        }
    
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        
        po = validated_data.get('purchase_order')
        if po and not validated_data.get('supplier'):
             validated_data['supplier'] = po.supplier
        # -------------------------------------------

        goods_receipt = GoodsReceipt.objects.create(**validated_data)
        
        for item_data in items_data:
            item_data.pop('purchase_order_item', None)
            GoodsReceiptItem.objects.create(goods_receipt=goods_receipt, **item_data)
        
        return goods_receipt

# Serializer for getting purchase order items for goods receipt
class PurchaseOrderItemForReceiptSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    quantity_remaining = serializers.SerializerMethodField()
    
    class Meta:
        model = PurchaseOrderItem
        fields = ['id', 'product', 'product_name', 'product_sku', 'quantity', 'unit_price', 'quantity_remaining']
    
    def get_quantity_remaining(self, obj):
        # Calculate quantity remaining to be received
        received_quantity = sum(
            item.quantity_received for item in obj.goodsreceiptitem_set.all()
        )
        return obj.quantity - received_quantity

class PurchaseOrderForReceiptSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    items = PurchaseOrderItemForReceiptSerializer(many=True, read_only=True)
    
    class Meta:
        model = PurchaseOrder
        fields = ['id', 'order_number', 'supplier', 'supplier_name', 'order_date', 'status', 'items']

class StockMovementSerializer(serializers.ModelSerializer):
    # Tambahkan field read-only untuk menampilkan nama, bukan hanya ID
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    user_name = serializers.CharField(source='user.username', read_only=True, allow_null=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True, allow_null=True)

    class Meta:
        model = StockMovement
        fields = [
            'id', 
            'product', 'product_name', 'product_sku',
            'location', 'location_name',
            'movement_type', 
            'quantity', 
            'unit_cost', 
            'reference_number', 
            'reference_type', 
            'notes', 
            'movement_date', 
            'user', 'user_name',
            'created_at', 'created_by', 'created_by_name'
        ]
        # Buat field relasi write-only agar tidak perlu mengirim objek lengkap dari frontend
        extra_kwargs = {
            'product': {'write_only': True},
            'location': {'write_only': True},
            'user': {'write_only': True},
            'created_by': {'write_only': True, 'required': False},
        }
