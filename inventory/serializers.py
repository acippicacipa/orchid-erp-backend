from rest_framework import serializers
from .models import (
    MainCategory, SubCategory, Category, Location, Product, Stock, 
    BillOfMaterials, BOMItem, AssemblyOrder, AssemblyOrderItem
)
from django.db import models

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
            'color', 'size', 'brand', 'model', 'cost_price', 'selling_price', 'discount',
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
    product_color = serializers.CharField(source='product.color', read_only=True, allow_blank=True)

    bom_items = BOMItemSerializer(many=True)

    class Meta:
        model = BillOfMaterials
        fields = [
            'id', 'product', 'product_name', 'product_sku', 'product_color', 'bom_number',
            'version', 'is_default', 'bom_items', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['bom_number', 'product_name', 'product_sku', 'product_color']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        
        # Di dalam serializer internal ini kita tambahkan 'component_color'
        class BOMItemDetailSerializer(serializers.ModelSerializer):
            component_name = serializers.CharField(source='component.name', read_only=True)
            component_sku = serializers.CharField(source='component.sku', read_only=True)
            
            # --- TAMBAHKAN FIELD BARU DI SINI ---
            component_color = serializers.CharField(source='component.color', read_only=True, allow_blank=True)
            
            class Meta:
                model = BOMItem
                # --- TAMBAHKAN 'component_color' KE DAFTAR FIELDS ---
                fields = [
                    'id', 
                    'component', 
                    'component_name', 
                    'component_sku', 
                    'component_color', # <-- Tambahkan di sini
                    'quantity', 
                    'notes'
                ]
        
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
    product_name = serializers.CharField(source='product.name', read_only=True, allow_null=True)
    product_color = serializers.CharField(source='product.color', read_only=True, allow_null=True)
    items = AssemblyOrderItemSerializer(many=True, read_only=True)
    production_location_name = serializers.CharField(source='production_location.code', read_only=True, allow_null=True)

    class Meta:
        model = AssemblyOrder
        fields = [
            'id', 
            'order_number',
            'product',          # Kirim ID Product ke sini
            'product_name', 'product_color',
            'bom',              # Kirim ID BOM ke sini
            'bom_number',
            'quantity',
            'quantity_produced',
            'production_location', # <-- INI FIELD YANG HARUS DIKIRIM DARI FRONTEND
            'production_location_name',
            'status',
            'priority',
            'order_date',
            'planned_start_date',
            'planned_completion_date',
            'description',
            'notes',
            'special_instructions',
            'assigned_to',
            'items'
        ]
        read_only_fields = ['order_number', 'product_name', 'bom_number', 'production_location_name']

    def create(self, validated_data):
        # Ambil data BOM dan kuantitas dari data yang sudah divalidasi
        bom = validated_data.get('bom')
        quantity_to_produce = validated_data.get('quantity')

        # Buat AssemblyOrder terlebih dahulu
        assembly_order = AssemblyOrder.objects.create(**validated_data)

        # Jika ada BOM dan kuantitas, buat item-itemnya
        if bom and quantity_to_produce > 0:
            # Ambil semua item dari BOM yang dipilih
            bom_items = bom.bom_items.all()

            # Loop melalui setiap item di BOM
            for bom_item in bom_items:
                # Hitung kuantitas komponen yang dibutuhkan
                required_quantity = bom_item.quantity * quantity_to_produce

                # Buat record AssemblyOrderItem
                AssemblyOrderItem.objects.create(
                    assembly_order=assembly_order,
                    component=bom_item.component,
                    quantity=required_quantity
                )
        
        return assembly_order

    # (Opsional) Anda juga bisa meng-override 'update' jika ingin logika yang sama saat mengedit
    def update(self, instance, validated_data):
        # Panggil update standar dari parent class
        instance = super().update(instance, validated_data)

        # Logika untuk meng-update item jika BOM atau kuantitas berubah
        bom = validated_data.get('bom', instance.bom)
        quantity_to_produce = validated_data.get('quantity', instance.quantity)

        # Hapus item lama dan buat yang baru (cara paling sederhana)
        instance.items.all().delete()

        if bom and quantity_to_produce > 0:
            for bom_item in bom.bom_items.all():
                required_quantity = bom_item.quantity * quantity_to_produce
                AssemblyOrderItem.objects.create(
                    assembly_order=instance,
                    component=bom_item.component,
                    quantity=required_quantity
                )
        
        return instance

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
    assembly_order_number = serializers.CharField(source='assembly_order.order_number', read_only=True, allow_null=True)
    
    class Meta:
        model = GoodsReceipt
        fields = [
            'id', 'receipt_number', 
            'purchase_order', 'purchase_order_number',
            'assembly_order', 'assembly_order_number', # <-- Tambahkan di sini
            'supplier', 'supplier_name', 
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
            'assembly_order', # <-- Tambahkan field baru
            'supplier', 
            'location',
            'received_by', 
            'notes', 
            'items'
        ]
        extra_kwargs = {
            'purchase_order': {'required': False, 'allow_null': True},
            'assembly_order': {'required': False, 'allow_null': True}, # <-- Buat opsional
            'supplier': {'required': False, 'allow_null': True},
            'location': {'required': True},
            'received_by': {'write_only': True}
        }
    
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        
        po = validated_data.get('purchase_order')
        if po and not validated_data.get('supplier'):
             validated_data['supplier'] = po.supplier

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

class AssemblyOrderForReceiptSerializer(serializers.ModelSerializer):
    """Serializer untuk menampilkan Assembly Orders yang siap diterima."""
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    # Menghitung sisa kuantitas yang belum diterima
    quantity_remaining = serializers.SerializerMethodField()

    class Meta:
        model = AssemblyOrder
        fields = [
            'id', 'order_number', 'product', 'product_name', 'product_sku', 
            'quantity', 'quantity_produced', 'quantity_remaining', 'production_location'
        ]

    def get_quantity_remaining(self, obj):
        # Hitung total yang sudah diterima melalui GoodsReceipts
        total_received = obj.goods_receipts.filter(status='CONFIRMED').aggregate(
            total=models.Sum('items__quantity_received')
        )['total'] or 0
        
        # Sisa adalah jumlah yang sudah diproduksi dikurangi yang sudah diterima
        remaining = obj.quantity_produced - total_received
        return remaining if remaining > 0 else 0
