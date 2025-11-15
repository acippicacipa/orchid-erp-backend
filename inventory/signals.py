from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from decimal import Decimal

# Impor model yang relevan
from .models import StockMovement, Stock, Product, Location

@receiver(post_save, sender=StockMovement)
def update_stock_on_movement(sender, instance, created, **kwargs):
    """
    Signal handler yang akan dipanggil setiap kali sebuah StockMovement disimpan.
    Jika movement baru ('created' is True), maka akan mengupdate Stock.
    """
    # Hanya jalankan logika jika ini adalah record BARU
    if not created:
        return

    # Gunakan transaction.atomic untuk memastikan operasi ini aman
    with transaction.atomic():
        # Dapatkan instance Stock yang relevan. Gunakan select_for_update() untuk mengunci baris
        # ini selama transaksi, mencegah race condition.
        stock, stock_created = Stock.objects.select_for_update().get_or_create(
            product=instance.product,
            location=instance.location,
            defaults={
                'quantity_on_hand': Decimal('0.00'),
                'quantity_sellable': Decimal('0.00'),
                # Ambil average_cost dari produk jika stok baru dibuat
                'average_cost': instance.product.cost_price or Decimal('0.00')
            }
        )

        # --- LOGIKA UTAMA: UPDATE KUANTITAS ---
        # Tambahkan kuantitas dari movement ke quantity_on_hand
        # instance.quantity bisa positif (masuk) atau negatif (keluar)
        stock.quantity_on_hand += instance.quantity

        # --- LOGIKA TAMBAHAN (Sangat Direkomendasikan) ---

        # 1. Update Quantity Sellable
        # Asumsi: semua pergerakan stok mempengaruhi stok yang bisa dijual,
        # kecuali jika itu adalah alokasi atau reservasi (yang ditangani terpisah).
        # Untuk transfer, receipt, adjustment, damage, dll., kita update quantity_sellable.
        if instance.movement_type not in ['ALLOCATION', 'RESERVATION']:
             stock.quantity_sellable += instance.quantity

        # 2. Update Average Cost (jika barang masuk/receipt)
        if instance.quantity > 0 and instance.unit_cost > 0:
            # Kalkulasi Weighted Average Cost
            old_total_value = (stock.quantity_on_hand - instance.quantity) * stock.average_cost
            new_item_value = instance.quantity * instance.unit_cost
            
            new_total_quantity = stock.quantity_on_hand
            
            if new_total_quantity > 0:
                stock.average_cost = (old_total_value + new_item_value) / new_total_quantity
            else:
                # Jika stok menjadi 0, average cost sama dengan unit cost terakhir
                stock.average_cost = instance.unit_cost
            
            # Update juga last_cost
            stock.last_cost = instance.unit_cost
            stock.last_received_date = instance.movement_date

        # 3. Update Last Sold Date (jika barang keluar/sale)
        if instance.movement_type == 'SALE':
            stock.last_sold_date = instance.movement_date

        # Simpan perubahan pada record Stock
        stock.save()

