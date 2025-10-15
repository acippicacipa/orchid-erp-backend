from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db.models import Q, Count, Avg
from django.utils import timezone
from datetime import datetime, timedelta

from accounts.permissions import IsAdminOrSales
from .discount_models import (
    CustomerGroup, ProductDiscount, QuantityDiscount, 
    WholesalerDiscount, DiscountCalculationService
)
from .discount_serializers import (
    CustomerGroupSerializer, ProductDiscountSerializer, 
    QuantityDiscountSerializer, WholesalerDiscountSerializer,
    PriceCalculationSerializer, PriceCalculationResponseSerializer,
    DiscountSummarySerializer
)
from inventory.models import Product

class CustomerGroupViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing customer groups
    """
    queryset = CustomerGroup.objects.all()
    serializer_class = CustomerGroupSerializer
    permission_classes = [IsAdminOrSales]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['group_type', 'is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'priority', 'margin_percentage']
    ordering = ['priority', 'name']

    @action(detail=False, methods=['get'])
    def active_groups(self, request):
        """Get all active customer groups"""
        active_groups = self.get_queryset().filter(is_active=True)
        serializer = self.get_serializer(active_groups, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def pricing_preview(self, request, pk=None):
        """Preview pricing for a customer group"""
        group = self.get_object()
        products = Product.objects.filter(is_active=True)[:10]  # Sample products
        
        pricing_data = []
        for product in products:
            group_price = group.calculate_selling_price(product.cost_price)
            pricing_data.append({
                'product_name': product.name,
                'product_sku': product.sku,
                'cost_price': product.cost_price,
                'regular_price': product.selling_price,
                'group_price': group_price,
                'margin_percentage': group.margin_percentage
            })
        
        return Response({
            'customer_group': group.name,
            'margin_percentage': group.margin_percentage,
            'pricing_preview': pricing_data
        })


class ProductDiscountViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing product discounts
    """
    queryset = ProductDiscount.objects.all()
    serializer_class = ProductDiscountSerializer
    permission_classes = [IsAdminOrSales]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['product', 'discount_type', 'is_active']
    search_fields = ['name', 'product__name', 'product__sku']
    ordering_fields = ['priority', 'start_date', 'end_date']
    ordering = ['priority', '-start_date']

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by active status
        active_only = self.request.query_params.get('active_only')
        if active_only == 'true':
            today = timezone.now().date()
            queryset = queryset.filter(
                is_active=True,
                start_date__lte=today,
                end_date__gte=today
            )
        
        return queryset

    @action(detail=False, methods=['get'])
    def active_discounts(self, request):
        """Get all currently active product discounts"""
        today = timezone.now().date()
        active_discounts = self.get_queryset().filter(
            is_active=True,
            start_date__lte=today,
            end_date__gte=today
        )
        serializer = self.get_serializer(active_discounts, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_product(self, request):
        """Get discounts for a specific product"""
        product_id = request.query_params.get('product_id')
        if not product_id:
            return Response({'error': 'Product ID is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        discounts = self.get_queryset().filter(product_id=product_id)
        serializer = self.get_serializer(discounts, many=True)
        return Response(serializer.data)


class QuantityDiscountViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing quantity discounts
    """
    queryset = QuantityDiscount.objects.all()
    serializer_class = QuantityDiscountSerializer
    permission_classes = [IsAdminOrSales]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['product', 'is_active']
    search_fields = ['name', 'product__name', 'product__sku']
    ordering_fields = ['priority', 'min_quantity']
    ordering = ['product', 'min_quantity']

    @action(detail=False, methods=['get'])
    def by_product(self, request):
        """Get quantity discounts for a specific product"""
        product_id = request.query_params.get('product_id')
        if not product_id:
            return Response({'error': 'Product ID is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        discounts = self.get_queryset().filter(product_id=product_id, is_active=True)
        serializer = self.get_serializer(discounts, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def calculate_discount(self, request):
        """Calculate quantity discount for given product and quantity"""
        product_id = request.data.get('product_id')
        quantity = request.data.get('quantity', 1)
        
        if not product_id:
            return Response({'error': 'Product ID is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)
        
        applicable_discounts = self.get_queryset().filter(
            product=product,
            is_active=True,
            min_quantity__lte=quantity
        ).filter(
            Q(max_quantity__isnull=True) | Q(max_quantity__gte=quantity)
        ).order_by('priority', '-min_quantity')
        
        if applicable_discounts.exists():
            discount = applicable_discounts.first()
            original_price = product.selling_price
            discount_amount = original_price * (discount.discount_percentage / 100)
            final_price = original_price - discount_amount
            
            return Response({
                'product_name': product.name,
                'quantity': quantity,
                'original_price': original_price,
                'discount_percentage': discount.discount_percentage,
                'discount_amount': discount_amount,
                'final_price': final_price,
                'discount_name': discount.name
            })
        else:
            return Response({
                'product_name': product.name,
                'quantity': quantity,
                'original_price': product.selling_price,
                'discount_percentage': 0,
                'discount_amount': 0,
                'final_price': product.selling_price,
                'discount_name': None
            })


class WholesalerDiscountViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing wholesaler discounts
    """
    queryset = WholesalerDiscount.objects.all()
    serializer_class = WholesalerDiscountSerializer
    permission_classes = [IsAdminOrSales]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['customer_group', 'is_active']
    search_fields = ['name', 'customer_group__name']
    ordering_fields = ['priority', 'start_date']
    ordering = ['priority', '-start_date']

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by active status
        active_only = self.request.query_params.get('active_only')
        if active_only == 'true':
            today = timezone.now().date()
            queryset = queryset.filter(
                is_active=True,
                start_date__lte=today,
                end_date__gte=today
            )
        
        return queryset

    @action(detail=False, methods=['get'])
    def by_customer_group(self, request):
        """Get wholesaler discounts for a specific customer group"""
        customer_group_id = request.query_params.get('customer_group_id')
        if not customer_group_id:
            return Response({'error': 'Customer group ID is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        today = timezone.now().date()
        discounts = self.get_queryset().filter(
            customer_group_id=customer_group_id,
            is_active=True,
            start_date__lte=today,
            end_date__gte=today
        )
        serializer = self.get_serializer(discounts, many=True)
        return Response(serializer.data)


class PriceCalculationViewSet(viewsets.ViewSet):
    """
    ViewSet for price calculation with hierarchical discount logic
    """
    permission_classes = [IsAdminOrSales]

    @action(detail=False, methods=['post'])
    def calculate_price(self, request):
        """Calculate final price with hierarchical discount logic"""
        serializer = PriceCalculationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        
        try:
            product = Product.objects.get(id=data['product_id'])
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)
        
        customer_group = None
        if data.get('customer_group_id'):
            try:
                customer_group = CustomerGroup.objects.get(id=data['customer_group_id'])
            except CustomerGroup.DoesNotExist:
                return Response({'error': 'Customer group not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Calculate price using hierarchical discount logic
        result = DiscountCalculationService.calculate_final_price(
            product=product,
            customer_group=customer_group,
            quantity=data['quantity'],
            order_date=data['order_date'],
            base_price=data.get('base_price')
        )
        
        response_data = {
            **result,
            'product_name': product.name,
            'product_sku': product.sku,
            'customer_group_name': customer_group.name if customer_group else None,
            'quantity': data['quantity'],
            'order_date': data['order_date']
        }
        
        response_serializer = PriceCalculationResponseSerializer(data=response_data)
        if response_serializer.is_valid():
            return Response(response_serializer.data)
        else:
            return Response(response_serializer.errors, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def bulk_calculate(self, request):
        """Calculate prices for multiple products"""
        items = request.data.get('items', [])
        if not items:
            return Response({'error': 'Items list is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        results = []
        for item in items:
            serializer = PriceCalculationSerializer(data=item)
            if serializer.is_valid():
                data = serializer.validated_data
                
                try:
                    product = Product.objects.get(id=data['product_id'])
                    customer_group = None
                    if data.get('customer_group_id'):
                        customer_group = CustomerGroup.objects.get(id=data['customer_group_id'])
                    
                    result = DiscountCalculationService.calculate_final_price(
                        product=product,
                        customer_group=customer_group,
                        quantity=data['quantity'],
                        order_date=data['order_date'],
                        base_price=data.get('base_price')
                    )
                    
                    results.append({
                        **result,
                        'product_id': product.id,
                        'product_name': product.name,
                        'product_sku': product.sku,
                        'customer_group_name': customer_group.name if customer_group else None,
                        'quantity': data['quantity'],
                        'order_date': data['order_date']
                    })
                except (Product.DoesNotExist, CustomerGroup.DoesNotExist) as e:
                    results.append({
                        'error': str(e),
                        'product_id': data.get('product_id')
                    })
            else:
                results.append({
                    'error': 'Invalid data',
                    'errors': serializer.errors
                })
        
        return Response({'results': results})

    @action(detail=False, methods=['get'])
    def discount_summary(self, request):
        """Get discount summary statistics"""
        today = timezone.now().date()
        
        # Count active discounts
        product_discounts_count = ProductDiscount.objects.filter(
            is_active=True,
            start_date__lte=today,
            end_date__gte=today
        ).count()
        
        quantity_discounts_count = QuantityDiscount.objects.filter(is_active=True).count()
        
        wholesaler_discounts_count = WholesalerDiscount.objects.filter(
            is_active=True,
            start_date__lte=today,
            end_date__gte=today
        ).count()
        
        active_customer_groups_count = CustomerGroup.objects.filter(is_active=True).count()
        
        # Products with discounts
        products_with_discounts = Product.objects.filter(
            Q(product_discounts__is_active=True) |
            Q(quantity_discounts__is_active=True)
        ).distinct().count()
        
        # Average discount percentage
        avg_discount = ProductDiscount.objects.filter(
            is_active=True,
            discount_type='PERCENTAGE',
            start_date__lte=today,
            end_date__gte=today
        ).aggregate(avg=Avg('discount_percentage'))['avg'] or 0
        
        # Recent discounts
        recent_discounts = ProductDiscount.objects.filter(
            is_active=True,
            start_date__lte=today,
            end_date__gte=today
        ).order_by('-created_at')[:5]
        
        recent_discounts_data = []
        for discount in recent_discounts:
            recent_discounts_data.append({
                'name': discount.name,
                'product_name': discount.product.name,
                'discount_type': discount.get_discount_type_display(),
                'discount_percentage': discount.discount_percentage,
                'start_date': discount.start_date,
                'end_date': discount.end_date
            })
        
        summary_data = {
            'product_discounts_count': product_discounts_count,
            'quantity_discounts_count': quantity_discounts_count,
            'wholesaler_discounts_count': wholesaler_discounts_count,
            'active_customer_groups_count': active_customer_groups_count,
            'total_products_with_discounts': products_with_discounts,
            'average_discount_percentage': round(avg_discount, 2),
            'recent_discounts': recent_discounts_data
        }
        
        serializer = DiscountSummarySerializer(data=summary_data)
        if serializer.is_valid():
            return Response(serializer.data)
        else:
            return Response(serializer.errors, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
