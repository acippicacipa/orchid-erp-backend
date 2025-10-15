from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from common.models import BaseModel
from inventory.models import Product

class CustomerGroup(BaseModel):
    """
    Customer Groups for pricing and discount management
    """
    GROUP_TYPES = [
        ('MBO', 'MBO (Margin 25%)'),
        ('REGULAR', 'Regular (Margin 10%)'),
        ('WHOLESALER', 'Wholesaler'),
        ('RETAIL', 'Retail'),
        ('VIP', 'VIP Customer'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    group_type = models.CharField(max_length=20, choices=GROUP_TYPES, default='REGULAR')
    description = models.TextField(blank=True, null=True)
    
    # Pricing Formula
    margin_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=10.00,
        help_text="Margin percentage over purchase price"
    )
    
    # Automatic Discount
    default_discount_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Default discount percentage for this group"
    )
    
    # Minimum order requirements
    minimum_order_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0.00,
        help_text="Minimum order amount to qualify for group pricing"
    )
    
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=1, help_text="Priority for discount calculation (1=highest)")

    class Meta:
        verbose_name = "Customer Group"
        verbose_name_plural = "Customer Groups"
        db_table = "sales_customer_groups"
        ordering = ['priority', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_group_type_display()})"

    def calculate_selling_price(self, purchase_price):
        """Calculate selling price based on group margin"""
        if not purchase_price:
            return Decimal('0.00')
        
        margin_multiplier = 1 + (self.margin_percentage / 100)
        return purchase_price * margin_multiplier


class ProductDiscount(BaseModel):
    """
    Master Product Discount - Override field for special promotions
    """
    DISCOUNT_TYPES = [
        ('PERCENTAGE', 'Percentage'),
        ('FIXED_AMOUNT', 'Fixed Amount'),
        ('SPECIAL_PRICE', 'Special Price'),
    ]
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='product_discounts')
    name = models.CharField(max_length=255, help_text="Discount name/description")
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES, default='PERCENTAGE')
    
    # Discount Values
    discount_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        blank=True, null=True
    )
    discount_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0.00,
        blank=True, null=True,
        help_text="Fixed discount amount in IDR"
    )
    special_price = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        blank=True, null=True,
        help_text="Special selling price in IDR"
    )
    
    # Validity Period
    start_date = models.DateField(help_text="Discount start date")
    end_date = models.DateField(help_text="Discount end date")
    
    # Conditions
    minimum_quantity = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=1.00,
        help_text="Minimum quantity to qualify for discount"
    )
    maximum_quantity = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        blank=True, null=True,
        help_text="Maximum quantity for discount (optional)"
    )
    
    # Customer Group Restrictions
    applicable_customer_groups = models.ManyToManyField(
        CustomerGroup, 
        blank=True,
        help_text="Leave empty to apply to all customer groups"
    )
    
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=1, help_text="Priority for discount calculation (1=highest)")

    class Meta:
        verbose_name = "Product Discount"
        verbose_name_plural = "Product Discounts"
        db_table = "sales_product_discounts"
        ordering = ['priority', '-start_date']

    def __str__(self):
        return f"{self.product.name} - {self.name}"

    def is_valid_for_date(self, check_date):
        """Check if discount is valid for given date"""
        return self.start_date <= check_date <= self.end_date

    def calculate_discounted_price(self, original_price, quantity=1):
        """Calculate discounted price based on discount type"""
        if not self.is_active:
            return original_price
            
        if self.minimum_quantity and quantity < self.minimum_quantity:
            return original_price
            
        if self.maximum_quantity and quantity > self.maximum_quantity:
            return original_price

        if self.discount_type == 'PERCENTAGE' and self.discount_percentage:
            discount_amount = original_price * (self.discount_percentage / 100)
            return original_price - discount_amount
        elif self.discount_type == 'FIXED_AMOUNT' and self.discount_amount:
            return max(original_price - self.discount_amount, Decimal('0.00'))
        elif self.discount_type == 'SPECIAL_PRICE' and self.special_price:
            return self.special_price
            
        return original_price


class QuantityDiscount(BaseModel):
    """
    Walk-in Quantity Discount - Tiered discounts based on item quantity
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='quantity_discounts')
    name = models.CharField(max_length=255, help_text="Quantity discount name")
    
    # Quantity Tiers
    min_quantity = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Minimum quantity for this tier"
    )
    max_quantity = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        blank=True, null=True,
        help_text="Maximum quantity for this tier (optional)"
    )
    
    # Discount
    discount_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Discount percentage for this quantity tier"
    )
    
    # Customer Group Restrictions
    applicable_customer_groups = models.ManyToManyField(
        CustomerGroup, 
        blank=True,
        help_text="Leave empty to apply to all customer groups"
    )
    
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=1, help_text="Priority for discount calculation (1=highest)")

    class Meta:
        verbose_name = "Quantity Discount"
        verbose_name_plural = "Quantity Discounts"
        db_table = "sales_quantity_discounts"
        ordering = ['product', 'min_quantity']

    def __str__(self):
        max_qty_str = f" - {self.max_quantity}" if self.max_quantity else "+"
        return f"{self.product.name} - Qty {self.min_quantity}{max_qty_str} ({self.discount_percentage}%)"

    def is_applicable_for_quantity(self, quantity):
        """Check if discount is applicable for given quantity"""
        if quantity < self.min_quantity:
            return False
        if self.max_quantity and quantity > self.max_quantity:
            return False
        return True


class WholesalerDiscount(BaseModel):
    """
    Wholesaler Discount - Automatic flat percentage based on customer level
    """
    customer_group = models.ForeignKey(CustomerGroup, on_delete=models.CASCADE, related_name='wholesaler_discounts')
    name = models.CharField(max_length=255, help_text="Wholesaler discount name")
    
    # Discount Configuration
    discount_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Flat discount percentage for this customer group"
    )
    
    # Minimum Requirements
    minimum_order_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0.00,
        help_text="Minimum order amount to qualify for wholesaler discount"
    )
    minimum_order_quantity = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=1.00,
        help_text="Minimum total quantity to qualify for wholesaler discount"
    )
    
    # Product Restrictions
    applicable_products = models.ManyToManyField(
        Product, 
        blank=True,
        help_text="Leave empty to apply to all products"
    )
    
    # Validity Period
    start_date = models.DateField(help_text="Discount start date")
    end_date = models.DateField(help_text="Discount end date")
    
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=1, help_text="Priority for discount calculation (1=highest)")

    class Meta:
        verbose_name = "Wholesaler Discount"
        verbose_name_plural = "Wholesaler Discounts"
        db_table = "sales_wholesaler_discounts"
        ordering = ['priority', 'customer_group']

    def __str__(self):
        return f"{self.customer_group.name} - {self.name} ({self.discount_percentage}%)"

    def is_valid_for_date(self, check_date):
        """Check if discount is valid for given date"""
        return self.start_date <= check_date <= self.end_date

    def is_applicable_for_order(self, order_amount, order_quantity):
        """Check if discount is applicable for given order"""
        if order_amount < self.minimum_order_amount:
            return False
        if order_quantity < self.minimum_order_quantity:
            return False
        return True


class DiscountCalculationService:
    """
    Service class for calculating hierarchical discounts
    """
    
    @staticmethod
    def calculate_final_price(product, customer_group, quantity, order_date, base_price=None):
        """
        Calculate final price with hierarchical discount logic
        Priority: Master Product Discount > Wholesaler Discount > Quantity Discount > Group Pricing
        """
        if base_price is None:
            base_price = product.selling_price
            
        final_price = base_price
        applied_discounts = []
        
        # 1. Check Master Product Discount (Highest Priority)
        product_discounts = ProductDiscount.objects.filter(
            product=product,
            is_active=True,
            start_date__lte=order_date,
            end_date__gte=order_date
        ).order_by('priority')
        
        for discount in product_discounts:
            if not discount.applicable_customer_groups.exists() or customer_group in discount.applicable_customer_groups.all():
                discounted_price = discount.calculate_discounted_price(final_price, quantity)
                if discounted_price < final_price:
                    final_price = discounted_price
                    applied_discounts.append({
                        'type': 'Product Discount',
                        'name': discount.name,
                        'discount_percentage': discount.discount_percentage,
                        'original_price': base_price,
                        'discounted_price': final_price
                    })
                    break  # Apply only the highest priority product discount
        
        # 2. Check Wholesaler Discount (if no product discount applied)
        if not applied_discounts:
            wholesaler_discounts = WholesalerDiscount.objects.filter(
                customer_group=customer_group,
                is_active=True,
                start_date__lte=order_date,
                end_date__gte=order_date
            ).order_by('priority')
            
            for discount in wholesaler_discounts:
                if not discount.applicable_products.exists() or product in discount.applicable_products.all():
                    discount_amount = final_price * (discount.discount_percentage / 100)
                    discounted_price = final_price - discount_amount
                    if discounted_price < final_price:
                        final_price = discounted_price
                        applied_discounts.append({
                            'type': 'Wholesaler Discount',
                            'name': discount.name,
                            'discount_percentage': discount.discount_percentage,
                            'original_price': base_price,
                            'discounted_price': final_price
                        })
                        break
        
        # 3. Check Quantity Discount (if no other discounts applied)
        if not applied_discounts:
            quantity_discounts = QuantityDiscount.objects.filter(
                product=product,
                is_active=True,
                min_quantity__lte=quantity
            ).filter(
                models.Q(max_quantity__isnull=True) | models.Q(max_quantity__gte=quantity)
            ).order_by('priority', '-min_quantity')
            
            for discount in quantity_discounts:
                if not discount.applicable_customer_groups.exists() or customer_group in discount.applicable_customer_groups.all():
                    discount_amount = final_price * (discount.discount_percentage / 100)
                    discounted_price = final_price - discount_amount
                    if discounted_price < final_price:
                        final_price = discounted_price
                        applied_discounts.append({
                            'type': 'Quantity Discount',
                            'name': discount.name,
                            'discount_percentage': discount.discount_percentage,
                            'min_quantity': discount.min_quantity,
                            'original_price': base_price,
                            'discounted_price': final_price
                        })
                        break
        
        # 4. Apply Group Customer Pricing (if no other discounts applied)
        if not applied_discounts and customer_group:
            group_price = customer_group.calculate_selling_price(product.cost_price)
            if group_price < final_price:
                final_price = group_price
                applied_discounts.append({
                    'type': 'Group Pricing',
                    'name': f"{customer_group.name} Pricing",
                    'margin_percentage': customer_group.margin_percentage,
                    'original_price': base_price,
                    'discounted_price': final_price
                })
        
        return {
            'final_price': final_price,
            'original_price': base_price,
            'total_discount': base_price - final_price,
            'applied_discounts': applied_discounts
        }
