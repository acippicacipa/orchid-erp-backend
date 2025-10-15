from rest_framework import serializers
from django.utils import timezone
from .discount_models import (
    CustomerGroup, ProductDiscount, QuantityDiscount, 
    WholesalerDiscount, DiscountCalculationService
)
from inventory.models import Product

class CustomerGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerGroup
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')

    def validate_margin_percentage(self, value):
        if value < 0 or value > 1000:
            raise serializers.ValidationError("Margin percentage must be between 0 and 1000%")
        return value

    def validate_default_discount_percentage(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Discount percentage must be between 0 and 100%")
        return value


class ProductDiscountSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    applicable_customer_group_names = serializers.StringRelatedField(
        source='applicable_customer_groups', 
        many=True, 
        read_only=True
    )
    
    class Meta:
        model = ProductDiscount
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')

    def validate(self, data):
        discount_type = data.get('discount_type')
        
        if discount_type == 'PERCENTAGE' and not data.get('discount_percentage'):
            raise serializers.ValidationError("Discount percentage is required for percentage discount type")
        elif discount_type == 'FIXED_AMOUNT' and not data.get('discount_amount'):
            raise serializers.ValidationError("Discount amount is required for fixed amount discount type")
        elif discount_type == 'SPECIAL_PRICE' and not data.get('special_price'):
            raise serializers.ValidationError("Special price is required for special price discount type")
        
        if data.get('start_date') and data.get('end_date'):
            if data['start_date'] > data['end_date']:
                raise serializers.ValidationError("Start date must be before end date")
        
        if data.get('minimum_quantity') and data.get('maximum_quantity'):
            if data['minimum_quantity'] > data['maximum_quantity']:
                raise serializers.ValidationError("Minimum quantity must be less than maximum quantity")
        
        return data


class QuantityDiscountSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    applicable_customer_group_names = serializers.StringRelatedField(
        source='applicable_customer_groups', 
        many=True, 
        read_only=True
    )
    
    class Meta:
        model = QuantityDiscount
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')

    def validate(self, data):
        if data.get('min_quantity') and data.get('max_quantity'):
            if data['min_quantity'] > data['max_quantity']:
                raise serializers.ValidationError("Minimum quantity must be less than maximum quantity")
        
        if data.get('discount_percentage'):
            if data['discount_percentage'] < 0 or data['discount_percentage'] > 100:
                raise serializers.ValidationError("Discount percentage must be between 0 and 100%")
        
        return data


class WholesalerDiscountSerializer(serializers.ModelSerializer):
    customer_group_name = serializers.CharField(source='customer_group.name', read_only=True)
    applicable_product_names = serializers.StringRelatedField(
        source='applicable_products', 
        many=True, 
        read_only=True
    )
    
    class Meta:
        model = WholesalerDiscount
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')

    def validate(self, data):
        if data.get('start_date') and data.get('end_date'):
            if data['start_date'] > data['end_date']:
                raise serializers.ValidationError("Start date must be before end date")
        
        if data.get('discount_percentage'):
            if data['discount_percentage'] < 0 or data['discount_percentage'] > 100:
                raise serializers.ValidationError("Discount percentage must be between 0 and 100%")
        
        return data


class PriceCalculationSerializer(serializers.Serializer):
    """
    Serializer for price calculation requests
    """
    product_id = serializers.IntegerField()
    customer_group_id = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, default=1)
    order_date = serializers.DateField(default=timezone.now().date())
    base_price = serializers.DecimalField(max_digits=15, decimal_places=2, required=False, allow_null=True)

    def validate_product_id(self, value):
        try:
            Product.objects.get(id=value)
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product not found")
        return value

    def validate_customer_group_id(self, value):
        if value is not None:
            try:
                CustomerGroup.objects.get(id=value)
            except CustomerGroup.DoesNotExist:
                raise serializers.ValidationError("Customer group not found")
        return value

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0")
        return value


class PriceCalculationResponseSerializer(serializers.Serializer):
    """
    Serializer for price calculation responses
    """
    final_price = serializers.DecimalField(max_digits=15, decimal_places=2)
    original_price = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_discount = serializers.DecimalField(max_digits=15, decimal_places=2)
    applied_discounts = serializers.ListField(child=serializers.DictField())
    
    product_name = serializers.CharField()
    product_sku = serializers.CharField()
    customer_group_name = serializers.CharField(allow_null=True)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2)
    order_date = serializers.DateField()


class DiscountSummarySerializer(serializers.Serializer):
    """
    Serializer for discount summary reports
    """
    product_discounts_count = serializers.IntegerField()
    quantity_discounts_count = serializers.IntegerField()
    wholesaler_discounts_count = serializers.IntegerField()
    active_customer_groups_count = serializers.IntegerField()
    
    total_products_with_discounts = serializers.IntegerField()
    average_discount_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    
    recent_discounts = serializers.ListField(child=serializers.DictField())
