from rest_framework import serializers
from .models import (
    MainCategory, SubCategory, Category, Location, Product, Stock, 
    BillOfMaterials, BOMItem, AssemblyOrder, AssemblyOrderItem, StockTransfer, StockTransferItem,
    ProductBundleComponent, ProductBundle
)
from django.db import models, transaction

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

class BulkMovementItemSerializer(serializers.Serializer):
    """Serializer untuk satu item di dalam bulk movement."""
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2)

    def validate_quantity(self, value):
        if value == 0:
            raise serializers.ValidationError("Quantity cannot be zero.")
        return value

class CreateBulkMovementSerializer(serializers.Serializer):
    """Serializer untuk memvalidasi payload create_bulk_movement."""
    movement_type = serializers.ChoiceField(choices=StockMovement.MOVEMENT_TYPES)
    location = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all())
    to_location = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all(), required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    reference_number = serializers.CharField(required=False, allow_blank=True)
    items = BulkMovementItemSerializer(many=True)

    def validate(self, data):
        """Validasi level objek."""
        movement_type = data.get('movement_type')
        location = data.get('location')
        to_location = data.get('to_location')

        if movement_type == 'TRANSFER':
            if not to_location:
                raise serializers.ValidationError({"to_location": "This field is required for TRANSFER movements."})
            if location == to_location:
                raise serializers.ValidationError("From and To locations cannot be the same for a transfer.")
        
        if not data.get('items'):
            raise serializers.ValidationError({"items": "At least one item is required."})
            
        return data

class InventoryProductSearchSerializer(serializers.ModelSerializer):
    """Serializer for product search in sales orders"""
    category_path = serializers.CharField(read_only=True)
    current_stock = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        read_only=True
    )
    
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
            'current_stock',
            'is_sellable', # Tambahkan ini untuk filtering di frontend jika perlu
            'unit_of_measure' # Ganti dari 'unit'
        ]

class StockTransferItemSerializer(serializers.ModelSerializer):
    # Gunakan PrimaryKeyRelatedField untuk input, tapi tampilkan nama untuk output
    product_name = serializers.CharField(source='product.full_name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)

    class Meta:
        model = StockTransferItem
        fields = [
            'id',
            'product', 
            'product_name',
            'product_sku',
            'quantity'
        ]
        # 'product' akan digunakan untuk menulis (menerima ID produk),
        # sedangkan 'product_name' dan 'product_sku' untuk membaca.

# Serializer utama untuk StockTransfer
class StockTransferSerializer(serializers.ModelSerializer):
    # Nested serializer untuk items. 'many=True' karena ada banyak item.
    items = StockTransferItemSerializer(many=True)
    
    # Representasi read-only untuk menampilkan nama, bukan hanya ID
    from_location_name = serializers.CharField(source='from_location.name', read_only=True)
    to_location_name = serializers.CharField(source='to_location.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True, default='')

    class Meta:
        model = StockTransfer
        fields = [
            'id',
            'transfer_number',
            'from_location',
            'from_location_name',
            'to_location',
            'to_location_name',
            'status',
            'notes',
            'created_by',
            'created_by_name',
            'created_at',
            'updated_at',
            'items' # Nested items
        ]
        # Definisikan field yang hanya untuk dibaca (read-only)
        read_only_fields = [
            'transfer_number', 
            'status', 
            'created_at', 
            'updated_at',
            'created_by'
        ]

    def validate(self, data):
        """
        Validasi level objek untuk memastikan lokasi tidak sama.
        """
        if data['from_location'] == data['to_location']:
            raise serializers.ValidationError("From and To locations cannot be the same.")
        
        if not data.get('items'):
            raise serializers.ValidationError({"items": "At least one item is required for a transfer."})
            
        return data

    def create(self, validated_data):
        """
        Override metode create untuk menangani pembuatan nested items.
        """
        items_data = validated_data.pop('items')
        
        with transaction.atomic():
            # Buat objek StockTransfer utama
            transfer = StockTransfer.objects.create(**validated_data)
            
            # Buat objek StockTransferItem untuk setiap item dalam data
            for item_data in items_data:
                StockTransferItem.objects.create(stock_transfer=transfer, **item_data)
                
        return transfer

class ProductBundleComponentSerializer(serializers.ModelSerializer):
    """
    Serializer untuk komponen yang digunakan dalam sebuah ProductBundle.
    Digunakan sebagai nested serializer di dalam ProductBundleSerializer.
    """
    # Read-only fields untuk menampilkan informasi di response
    component_name = serializers.CharField(source='component.name', read_only=True)
    component_sku = serializers.CharField(source='component.sku', read_only=True)

    class Meta:
        model = ProductBundleComponent
        fields = [
            'id', 
            'component',      # ID produk komponen untuk write operations
            'component_name', # Untuk display (read-only)
            'component_sku',  # Untuk display (read-only)
            'quantity_used', 
            'unit_cost'       # Akan diisi oleh sistem, jadi read-only saat create
        ]
        read_only_fields = ['unit_cost']
        # Pastikan 'component' bisa ditulis (writeable) saat membuat
        extra_kwargs = {
            'component': {'write_only': False} 
        }


class ProductBundleSerializer(serializers.ModelSerializer):
    """
    Serializer utama untuk ProductBundle.
    Menangani nested creation untuk komponen-komponennya.
    Logika utama proses bundling terjadi di ViewSet, bukan di sini.
    Serializer ini lebih fokus pada validasi dan representasi data.
    """
    # Nested serializer untuk menerima dan menampilkan komponen
    components = ProductBundleComponentSerializer(many=True)

    # Read-only fields untuk menampilkan informasi relasi di frontend
    product_name = serializers.CharField(source='product.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = ProductBundle
        fields = [
            'id', 'bundle_number', 'product', 'product_name', 'quantity_created',
            'location', 'location_name', 'bundle_date', 'total_component_cost',
            'notes', 'created_by', 'created_by_name', 'created_at', 'components'
        ]
        read_only_fields = [
            'bundle_number', 
            'total_component_cost', 
            'created_by', 
            'created_by_name',
            'created_at'
        ]

    def validate_product(self, value):
        """Validasi bahwa produk yang dipilih adalah produk bundle."""
        if not value.is_bundle:
            raise serializers.ValidationError("The selected product is not marked as a bundle.")
        return value

    def validate_components(self, value):
        """Validasi bahwa daftar komponen tidak kosong."""
        if not value:
            raise serializers.ValidationError("At least one component is required.")
        return value

    def create(self, validated_data):
        """
        Override metode create.
        Logika utama (StockMovement, Jurnal) akan ditangani di ViewSet.
        Di sini kita hanya membuat record ProductBundle dan komponennya.
        """
        # Pisahkan data komponen dari data utama
        components_data = validated_data.pop('components')
        
        # Buat objek ProductBundle utama
        bundle = ProductBundle.objects.create(**validated_data)
        
        # Loop melalui data komponen dan buat objek ProductBundleComponent
        for component_data in components_data:
            ProductBundleComponent.objects.create(bundle=bundle, **component_data)
        
        return bundle