# sales/services.py

from decimal import Decimal

class PricingService:
    """
    Service class to handle complex pricing and discount logic for sales orders.
    """
    
    @staticmethod
    def get_price_and_discount(customer, product, quantity):
        """
        Calculates the final unit price and discount percentage for a given item.
        
        Returns: A dictionary {'unit_price': Decimal, 'discount_percentage': Decimal}
        """
        unit_price = product.selling_price
        discount_percentage = Decimal('0.00')
        
        if not customer or not customer.customer_group:
            # Jika tidak ada customer atau grup, gunakan harga dan diskon standar produk
            discount_percentage = product.discount
            return {'unit_price': unit_price, 'discount_percentage': discount_percentage}

        group_name = customer.customer_group.name.lower()
        
        # --- LOGIKA 1: Harga Khusus untuk 'Orchid Grup' ---
        if 'orchid grup' in group_name:
            main_category_name = product.main_category.name.lower() if product.main_category else ''
            
            if 'mbo' in main_category_name:
                # Harga = Cost Price + 25%
                unit_price = product.cost_price * Decimal('1.25')
            else:
                # Harga = Cost Price + 10%
                unit_price = product.cost_price * Decimal('1.10')
            
            # Grup Orchid tidak mendapat diskon tambahan
            discount_percentage = Decimal('0.00')

        # --- LOGIKA 2: Diskon Kuantitas untuk 'Walk In' ---
        elif 'walk in' in group_name:
            if quantity >= 12:
                discount_percentage = Decimal('15.00')
            elif quantity >= 6:
                discount_percentage = Decimal('10.00')
            elif quantity >= 3:
                discount_percentage = Decimal('5.00')
            
            # Bandingkan dengan diskon produk, ambil yang lebih besar
            discount_percentage = max(discount_percentage, product.discount)

        # --- LOGIKA 3: Diskon Grup untuk 'Grosir' ---
        elif 'grosir' in group_name:
            group_discount = customer.customer_group.discount_percentage
            product_discount = product.discount
            
            # Ambil diskon yang nilainya lebih besar
            discount_percentage = max(group_discount, product_discount)
            
        else:
            # Untuk grup lain, gunakan diskon produk sebagai default
            discount_percentage = product.discount

        return {
            'unit_price': unit_price.quantize(Decimal('0.01')),
            'discount_percentage': discount_percentage.quantize(Decimal('0.01'))
        }
