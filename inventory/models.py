from django.utils import timezone
from django.db import models
from django.conf import settings
from common.models import BaseModel
from datetime import date

class MainCategory(models.Model):
    """
    Main Category model untuk kategori utama seperti 'Barang Lokal' dan 'Barang Import'
    """
    name = models.CharField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Main Category"
        verbose_name_plural = "Main Categories"
        db_table = "inventory_main_categories"

    def __str__(self):
        return self.name

class SubCategory(models.Model):
    """
    Sub Category model untuk sub kategori seperti 'Bunga', 'Daun', 'Aksesoris'
    """
    name = models.CharField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sub Category"
        verbose_name_plural = "Sub Categories"
        db_table = "inventory_sub_categories"

    def __str__(self):
        return self.name

class Category(BaseModel):
    """
    Category model yang menghubungkan Main Category dan Sub Category
    Setiap produk akan memiliki 1 Main Category dan 1 Sub Category
    """
    name = models.CharField(max_length=100, db_index=True)
    main_category = models.ForeignKey(MainCategory, on_delete=models.CASCADE, related_name="categories", null=True, blank=True)
    sub_category = models.ForeignKey(SubCategory, on_delete=models.CASCADE, related_name="categories", null=True, blank=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Category"
        verbose_name_plural = "Categories"
        db_table = "inventory_categories"
        unique_together = ("main_category", "sub_category")

    def __str__(self):
        main_name = self.main_category.name if self.main_category else "No Main Category"
        sub_name = self.sub_category.name if self.sub_category else "No Sub Category"
        return f"{main_name} - {sub_name}"
    
    @property
    def full_path(self):
        """Return the full category path"""
        main_name = self.main_category.name if self.main_category else "No Main Category"
        sub_name = self.sub_category.name if self.sub_category else "No Sub Category"
        return f"{main_name} > {sub_name}"

class Location(BaseModel):
    LOCATION_TYPES = [
        ("WAREHOUSE", "Main Warehouse"),
        ("STORE_ONLINE", "Online Store"),
        ("STORE_OFFLINE", "Offline Store"),
        ("PRODUCTION", "Production Area"),
        ("QUARANTINE", "Quarantine Area"),
        ("TRANSIT", "In Transit"),
        ("SUPPLIER", "Supplier Location"),
        ("CUSTOMER", "Customer Location"),
        ('CONSIGNMENT', 'Consignment'),
    ]
    
    name = models.CharField(max_length=100, unique=True, db_index=True)
    location_type = models.CharField(max_length=20, choices=LOCATION_TYPES, default="WAREHOUSE")
    code = models.CharField(max_length=20, unique=True, db_index=True)
    address = models.TextField(blank=True, null=True)
    contact_person = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    
    is_active = models.BooleanField(default=True)
    is_sellable_location = models.BooleanField(default=True, help_text="Can sell from this location")
    is_purchasable_location = models.BooleanField(default=True, help_text="Can receive purchases at this location")
    is_manufacturing_location = models.BooleanField(default=False, help_text="Manufacturing/Assembly location")
    
    storage_capacity = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Storage capacity in cubic units")
    current_utilization = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="Current utilization percentage")
    
    notes = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Location"
        verbose_name_plural = "Locations"
        db_table = "inventory_locations"
        indexes = [
            models.Index(fields=["location_type", "is_active"]),
            models.Index(fields=["code"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"
    
    @property
    def display_name(self):
        return f"{self.name} - {self.get_location_type_display()}"

class Product(BaseModel):
    name = models.CharField(max_length=255, db_index=True)
    sku = models.CharField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True, null=True)
    
    # Setiap produk memiliki 1 Main Category dan 1 Sub Category
    main_category = models.ForeignKey(MainCategory, on_delete=models.SET_NULL, null=True, blank=True)
    sub_category = models.ForeignKey(SubCategory, on_delete=models.SET_NULL, null=True, blank=True)
    
    color = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    size = models.CharField(max_length=50, blank=True, null=True)
    brand = models.CharField(max_length=100, blank=True, null=True)
    model = models.CharField(max_length=100, blank=True, null=True)
    
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)

    discount = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0.00, 
        help_text="Product-specific discount percentage. Overrides group discount if higher."
    )
    
    unit_of_measure = models.CharField(max_length=50, default="pcs")
    weight = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    dimensions = models.CharField(max_length=100, blank=True, null=True, help_text="L x W x H")
    
    is_active = models.BooleanField(default=True)
    is_sellable = models.BooleanField(default=True)
    is_purchasable = models.BooleanField(default=True)
    is_manufactured = models.BooleanField(default=False)
    is_bundle = models.BooleanField(default=False, help_text="Is this product a result of bundling/kitting?")
    
    minimum_stock_level = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    maximum_stock_level = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    reorder_point = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    barcode = models.CharField(max_length=100, blank=True, null=True)
    supplier_code = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"
        db_table = "inventory_products"
        indexes = [
            models.Index(fields=["name", "sku"]),
            models.Index(fields=["main_category", "sub_category", "is_active"]),
            models.Index(fields=["color", "size"]),
        ]

    def __str__(self):
        color_info = f" - {self.color}" if self.color else ""
        size_info = f" - {self.size}" if self.size else ""
        return f"{self.name}{color_info}{size_info} ({self.sku})"
    
    @property
    def full_name(self):
        parts = [self.name]
        if self.brand:
            parts.append(f"Brand: {self.brand}")
        if self.color:
            parts.append(f"{self.color}")
        if self.size:
            parts.append(f"Size: {self.size}")
        return " ".join(parts)
    
    @property
    def category_path(self):
        if self.main_category and self.sub_category:
            return f"{self.main_category.name} > {self.sub_category.name}"
        return "Uncategorized"

class Stock(BaseModel):

    OWNERSHIP_CHOICES = [
        ('OWNED', 'Owned'),
        ('CONSIGNED', 'Consigned'),
    ]
    ownership_status = models.CharField(
        max_length=20, 
        choices=OWNERSHIP_CHOICES, 
        default='OWNED'
    )

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="stock_levels")
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="stock_items")
    
    quantity_on_hand = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    quantity_sellable = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    quantity_non_sellable = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    quantity_reserved = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    quantity_allocated = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    average_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    last_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    last_received_date = models.DateTimeField(null=True, blank=True)
    last_sold_date = models.DateTimeField(null=True, blank=True)
    last_counted_date = models.DateTimeField(null=True, blank=True)
    
    bin_location = models.CharField(max_length=50, blank=True, null=True, help_text="Specific bin/shelf location")
    lot_number = models.CharField(max_length=50, blank=True, null=True)
    expiry_date = models.DateField(null=True, blank=True)
    
    notes = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Stock"
        verbose_name_plural = "Stock"
        unique_together = ('product', 'location', 'ownership_status')
        db_table = "inventory_stock"

    def __str__(self):
        #return f"{self.product.name} at {self.location.name}: {self.quantity_on_hand} ({self.quantity_sellable} sellable)"
        return f"{self.product.name} at {self.location.name} ({self.ownership_status})"

class BillOfMaterials(BaseModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="boms")
    bom_number = models.CharField(max_length=50, db_index=True, blank=True)
    version = models.CharField(max_length=20, default="1.0")
    is_default = models.BooleanField(default=False, help_text="Default BOM for this product")

    class Meta:
        verbose_name = "Bill of Materials"
        verbose_name_plural = "Bills of Materials"
        db_table = "inventory_bom"
        unique_together = ("product", "version")

    def __str__(self):
        return f"BOM-{self.bom_number or 'NEW'}: {self.product.name} v{self.version}"

    def save(self, *args, **kwargs):
        # Cek jika ini adalah objek baru (belum punya ID) dan bom_number masih kosong
        if not self.pk and not self.bom_number:
            # Panggil save() pertama kali untuk mendapatkan ID dari database
            super().save(*args, **kwargs) 
            
            # Sekarang kita punya self.pk (ID), kita bisa membuat bom_number
            # Format: BOM-000001, BOM-000002, dst.
            self.bom_number = f"BOM-{self.pk:06d}"
            
            # Panggil save() lagi untuk menyimpan bom_number yang baru dibuat
            # Kita hanya update field bom_number untuk efisiensi
            kwargs['force_insert'] = False # Pastikan ini bukan insert lagi
            super().save(update_fields=['bom_number'], *args, **kwargs)
        else:
            # Jika ini adalah update, atau bom_number sudah ada, jalankan save() biasa
            super().save(*args, **kwargs)

class BOMItem(BaseModel):
    bom = models.ForeignKey(BillOfMaterials, on_delete=models.CASCADE, related_name="bom_items")
    component = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "BOM Item"
        verbose_name_plural = "BOM Items"
        db_table = "inventory_bom_items"

    def __str__(self):
        return f"{self.quantity} of {self.component.name} for {self.bom.product.name}"

def get_current_jakarta_date():
    return timezone.now().date()

class AssemblyOrder(BaseModel):
    """
    Model untuk mengelola perintah perakitan/produksi.
    """
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PLANNED', 'Planned'),
        ('RELEASED', 'Released'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
        ('ON_HOLD', 'On Hold'),
    ]

    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('NORMAL', 'Normal'),
        ('HIGH', 'High'),
        ('URGENT', 'Urgent'),
    ]

    # --- FIELD BARU & YANG DIPERBAIKI ---

    # Nomor Order yang dibuat otomatis
    order_number = models.CharField(max_length=50, unique=True, db_index=True, blank=True)

    # Relasi langsung ke produk yang akan dibuat. Ini menyederhanakan banyak hal.
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='assembly_orders')
    
    # BOM yang digunakan. Bisa null jika produk sederhana tidak butuh BOM.
    bom = models.ForeignKey(BillOfMaterials, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Kuantitas yang akan diproduksi
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Kuantitas yang sudah selesai diproduksi
    quantity_produced = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    # Lokasi produksi
    production_location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, limit_choices_to={'is_manufacturing_location': True})

    # Status dan Prioritas
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', db_index=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='NORMAL', db_index=True)

    # Tanggal-tanggal penting
    order_date = models.DateField(default=date.today)
    planned_start_date = models.DateField(null=True, blank=True)
    planned_completion_date = models.DateField(null=True, blank=True)
    actual_start_date = models.DateTimeField(null=True, blank=True)
    actual_completion_date = models.DateTimeField(null=True, blank=True)

    # Field teks tambahan
    description = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    special_instructions = models.TextField(blank=True)
    
    # Pengguna yang bertanggung jawab
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assembly_tasks')

    class Meta:
        db_table = "inventory_assembly_orders"
        verbose_name = "Assembly Order"
        verbose_name_plural = "Assembly Orders"
        ordering = ['-order_date', '-created_at']

    def __str__(self):
        return f"{self.order_number}: {self.quantity} of {self.product.name}"

    def save(self, *args, **kwargs):
        # Generate order_number jika ini adalah objek baru
        if not self.order_number:
            last_order = AssemblyOrder.objects.order_by('-id').first()
            new_id = (last_order.id + 1) if last_order else 1
            self.order_number = f"AO-{new_id:06d}"
        
        # Pastikan produk dari BOM (jika ada) cocok dengan produk di order
        if self.bom and self.bom.product != self.product:
            raise ValueError("Product in Assembly Order does not match the product in the selected BOM.")

        super().save(*args, **kwargs)

class AssemblyOrderItem(BaseModel):
    assembly_order = models.ForeignKey(AssemblyOrder, on_delete=models.CASCADE, related_name="items")
    component = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "inventory_assembly_order_items"

    def __str__(self):
        return f"{self.quantity} of {self.component.name} for Assembly Order {self.assembly_order.id}"


# Goods Receipt Models for receiving items from Purchase Orders
class GoodsReceipt(BaseModel):
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('CONFIRMED', 'Confirmed'),
        ('COMPLETED', 'Completed'),
    ]

    receipt_number = models.CharField(max_length=50, unique=True, editable=False)
    purchase_order = models.ForeignKey(
        'purchasing.PurchaseOrder', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='goods_receipts'
    )
    
    assembly_order = models.ForeignKey(
        'AssemblyOrder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='goods_receipts',
        help_text="Sumber penerimaan barang dari hasil produksi."
    )

    supplier = models.ForeignKey(
        'purchasing.Supplier',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Supplier pengirim barang. Otomatis terisi jika dari PO, bisa diisi manual jika tanpa PO."
    )
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True)
    receipt_date = models.DateField(default=get_current_jakarta_date)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, # <-- UBAH INI
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    notes = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Goods Receipt"
        verbose_name_plural = "Goods Receipts"
        db_table = "inventory_goods_receipts"
        ordering = ['-receipt_date', '-created_at']

    def __str__(self):
        return f"GR-{self.receipt_number} - PO {self.purchase_order.order_number}"

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            # Logika pembuatan receipt_number Anda
            last_receipt = GoodsReceipt.objects.order_by('id').last()
            if not last_receipt:
                self.receipt_number = 'GR-00001'
            else:
                receipt_int = int(last_receipt.receipt_number.split('-')[-1])
                new_receipt_int = receipt_int + 1
                self.receipt_number = f'GR-{new_receipt_int:05d}'
        super().save(*args, **kwargs)

class GoodsReceiptItem(BaseModel):
    goods_receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name='items')
    purchase_order_item = models.ForeignKey(
        'purchasing.PurchaseOrderItem',
        on_delete=models.SET_NULL, # Ganti ke SET_NULL agar jika PO Item dihapus, GR Item tidak ikut terhapus
        null=True,                 # Izinkan nilai NULL di database
        blank=True                 # Izinkan field ini kosong di form/serializer Django
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity_ordered = models.DecimalField(max_digits=12, decimal_places=2)
    quantity_received = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    batch_number = models.CharField(max_length=100, blank=True, null=True)
    expiry_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Goods Receipt Item"
        verbose_name_plural = "Goods Receipt Items"
        db_table = "inventory_goods_receipt_items"

    def __str__(self):
        return f"{self.goods_receipt.receipt_number} - {self.product.name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        
        # Update product stock when goods receipt item is confirmed
        if self.goods_receipt.status == 'CONFIRMED':
            # Get or create stock record for this product and location
            stock, created = Stock.objects.get_or_create(
                product=self.product,
                location=self.location or Location.objects.filter(is_active=True).first(),
                defaults={
                    'quantity_on_hand': 0,
                    'quantity_sellable': 0,
                    'average_cost': self.unit_price,
                    'last_cost': self.unit_price,
                }
            )
            
            # Update stock quantities
            stock.quantity_on_hand += self.quantity_received
            stock.quantity_sellable += self.quantity_received
            stock.last_cost = self.unit_price
            stock.last_received_date = timezone.now()
            
            # Update average cost using weighted average
            total_value = (stock.quantity_on_hand - self.quantity_received) * stock.average_cost + self.quantity_received * self.unit_price
            stock.average_cost = total_value / stock.quantity_on_hand if stock.quantity_on_hand > 0 else self.unit_price
            
            stock.save()

class StockTransfer(BaseModel):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN_TRANSIT', 'In Transit'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]
    transfer_number = models.CharField(max_length=50, unique=True, blank=True)
    from_location = models.ForeignKey('Location', related_name='transfers_out', on_delete=models.PROTECT)
    to_location = models.ForeignKey('Location', related_name='transfers_in', on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    notes = models.TextField(blank=True, null=True)
    # Tambahkan field user jika perlu
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='stock_transfers_created')
    
    def save(self, *args, **kwargs):
        if not self.transfer_number:
            # Logika pembuatan nomor transfer
            today_str = timezone.now().strftime('%Y%m%d')
            last_transfer = StockTransfer.objects.filter(transfer_number__startswith=f"TR-{today_str}").order_by('transfer_number').last()
            new_num = 1
            if last_transfer:
                last_num_str = last_transfer.transfer_number.split('-')[-1]
                new_num = int(last_num_str) + 1
            self.transfer_number = f"TR-{today_str}-{new_num:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.transfer_number

class StockTransferItem(BaseModel):
    stock_transfer = models.ForeignKey(StockTransfer, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey('Product', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.product.name} ({self.quantity}) for {self.stock_transfer.transfer_number}"

# --- MODIFIKASI MODEL StockMovement ---
# Model ini sekarang menjadi lebih generik dan kuat

class StockMovement(BaseModel):
    MOVEMENT_TYPES = [
        ('RECEIPT', 'Goods Receipt'),
        ('SALE', 'Sale'),
        ('ADJUSTMENT', 'Stock Adjustment'),
        ('TRANSFER_OUT', 'Transfer Out'), # Lebih spesifik
        ('TRANSFER_IN', 'Transfer In'),   # Lebih spesifik
        ('RETURN', 'Return'),
        ('DAMAGE', 'Damage/Loss'),
        ('SALES_RETURN', 'Sales Return'),
        ('PURCHASE_RETURN', 'Purchase Return'),
    ]

    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='movements')
    location = models.ForeignKey('Location', on_delete=models.CASCADE, related_name='movements')
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    quantity = models.DecimalField(max_digits=12, decimal_places=2) # Negatif untuk keluar, Positif untuk masuk
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Reference fields untuk melacak sumber pergerakan
    reference_number = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    reference_type = models.CharField(max_length=50, blank=True, null=True) # Misal: 'STOCK_TRANSFER', 'SALES_ORDER'
    
    notes = models.TextField(blank=True, null=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    movement_date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-movement_date', '-created_at']

    def __str__(self):
        return f"{self.product.name} - {self.movement_type} - {self.quantity} at {self.location.name}"

class ProductBundle(BaseModel):
    """Mencatat transaksi perakitan/bundling produk."""
    bundle_number = models.CharField(max_length=50, unique=True, blank=True)
    
    # Produk hasil rakitan
    product = models.ForeignKey(
        Product, 
        on_delete=models.PROTECT, 
        related_name='bundles_created',
        limit_choices_to={'is_bundle': True}
    )
    quantity_created = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Lokasi tempat proses terjadi
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    
    bundle_date = models.DateField(default=timezone.now)
    total_component_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    notes = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.bundle_number:
            prefix = f"BNDL-{self.bundle_date.year}-"
            last_bundle = ProductBundle.objects.filter(bundle_number__startswith=prefix).order_by('bundle_number').last()
            last_num = int(last_bundle.bundle_number.split('-')[-1]) if last_bundle else 0
            self.bundle_number = f"{prefix}{last_num + 1:05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.bundle_number

class ProductBundleComponent(BaseModel):
    """Komponen yang digunakan dalam sebuah transaksi bundling."""
    bundle = models.ForeignKey(ProductBundle, on_delete=models.CASCADE, related_name='components')
    component = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity_used = models.DecimalField(max_digits=10, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, help_text="Cost of the component at the time of bundling")

    def __str__(self):
        return f"{self.component.name} for {self.bundle.bundle_number}"