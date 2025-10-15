from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny
from django.db.models import Q, F
from accounts.permissions import IsAdminOrWarehouse
from .models import (
    MainCategory, SubCategory, Category, Location, Product, Stock, 
    BillOfMaterials, BOMItem, AssemblyOrder, AssemblyOrderItem
)
from .serializers import (
    MainCategorySerializer, SubCategorySerializer, CategorySerializer, 
    LocationSerializer, ProductSerializer, StockSerializer,
    BillOfMaterialsSerializer, BOMItemSerializer, 
    AssemblyOrderSerializer, AssemblyOrderItemSerializer
)

class MainCategoryViewSet(viewsets.ModelViewSet):
    queryset = MainCategory.objects.all()
    serializer_class = MainCategorySerializer
    permission_classes = [IsAdminOrWarehouse]

    def get_queryset(self):
        queryset = MainCategory.objects.all()
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )
        return queryset.order_by('name')

class SubCategoryViewSet(viewsets.ModelViewSet):
    queryset = SubCategory.objects.all()
    serializer_class = SubCategorySerializer
    permission_classes = [IsAdminOrWarehouse]

    def get_queryset(self):
        queryset = SubCategory.objects.all()
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )
        return queryset.order_by('name')

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrWarehouse]

    def get_queryset(self):
        queryset = Category.objects.select_related('main_category', 'sub_category').all()
        search = self.request.query_params.get('search', None)
        main_category = self.request.query_params.get('main_category', None)
        sub_category = self.request.query_params.get('sub_category', None)
        
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(main_category__name__icontains=search) |
                Q(sub_category__name__icontains=search) |
                Q(description__icontains=search)
            )
        
        if main_category:
            queryset = queryset.filter(main_category_id=main_category)
            
        if sub_category:
            queryset = queryset.filter(sub_category_id=sub_category)
            
        return queryset.order_by('main_category__name', 'sub_category__name')

class LocationViewSet(viewsets.ModelViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer
    permission_classes = [IsAdminOrWarehouse]

    def get_queryset(self):
        queryset = Location.objects.all()
        search = self.request.query_params.get('search', None)
        location_type = self.request.query_params.get('location_type', None)
        is_active = self.request.query_params.get('is_active', None)
        
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(code__icontains=search) |
                Q(address__icontains=search)
            )
        
        if location_type:
            queryset = queryset.filter(location_type=location_type)
            
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
            
        return queryset.order_by('name')

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsAdminOrWarehouse]

    def get_queryset(self):
        queryset = Product.objects.select_related('main_category', 'sub_category').all()
        search = self.request.query_params.get('search', None)
        main_category = self.request.query_params.get('main_category', None)
        sub_category = self.request.query_params.get('sub_category', None)
        color = self.request.query_params.get('color', None)
        is_active = self.request.query_params.get('is_active', None)
        
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(sku__icontains=search) |
                Q(description__icontains=search) |
                Q(barcode__icontains=search)
            )
        
        if main_category:
            queryset = queryset.filter(main_category_id=main_category)
            
        if sub_category:
            queryset = queryset.filter(sub_category_id=sub_category)
            
        if color:
            queryset = queryset.filter(color__icontains=color)
            
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
            
        return queryset.order_by('name')

    @action(detail=False, methods=['get'])
    def colors(self, request):
        """Get all unique colors"""
        colors = Product.objects.exclude(color__isnull=True).exclude(color='').values_list('color', flat=True).distinct()
        return Response({'colors': list(colors)})

    @action(detail=False, methods=['get'])
    def sizes(self, request):
        """Get all unique sizes"""
        sizes = Product.objects.exclude(size__isnull=True).exclude(size='').values_list('size', flat=True).distinct()
        return Response({'sizes': list(sizes)})

class StockViewSet(viewsets.ModelViewSet):
    queryset = Stock.objects.all()
    serializer_class = StockSerializer
    permission_classes = [AllowAny] # Ganti ke IsAdminOrWarehouse jika sudah siap

    # --- LOGIKA LAMA ANDA (TETAP DIPERTAHANKAN) ---
    def get_queryset(self):
        queryset = Stock.objects.select_related('product', 'location').all()
        product = self.request.query_params.get('product', None)
        location = self.request.query_params.get('location', None)
        low_stock = self.request.query_params.get('low_stock', None)
        
        if product:
            queryset = queryset.filter(product_id=product)
            
        if location:
            queryset = queryset.filter(location_id=location)
            
        if low_stock and low_stock.lower() == 'true':
            # Filter for products where current stock is below minimum level
            queryset = queryset.filter(
                quantity_on_hand__lt=F('product__minimum_stock_level')
            )
            
        return queryset.order_by('product__name', 'location__name')

    # --- LOGIKA LAMA ANDA (TETAP DIPERTAHANKAN) ---
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get stock summary by location"""
        from django.db.models import Sum, Count
        
        summary = Stock.objects.values('location__name').annotate(
            total_products=Count('product', distinct=True),
            total_quantity=Sum('quantity_on_hand'),
            sellable_quantity=Sum('quantity_sellable')
        ).order_by('location__name')
        
        return Response({'summary': list(summary)})

    # ==============================================================================
    # 2. TAMBAHKAN CUSTOM ACTION BARU DI SINI
    # ==============================================================================
    @action(detail=False, methods=['post'], url_path='receive')
    def receive_stock(self, request):
        """
        Custom action untuk menerima stok.
        Akses: POST /api/inventory/stock/receive/
        """
        product_id = request.data.get('product')
        location_id = request.data.get('location')
        quantity = request.data.get('quantity')
        unit_cost = request.data.get('unit_cost')
        notes = request.data.get('notes')

        if not all([product_id, location_id, quantity]):
            return Response(
                {"detail": "Product, location, and quantity are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Panggil fungsi service yang sudah Anda buat
            movement = StockService.receive_stock(
                product_id=product_id,
                location_id=location_id,
                quantity=quantity,
                unit_cost=unit_cost,
                notes=notes
            )
            return Response(
                {"detail": "Stock received successfully.", "movement_id": movement.id},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='sell')
    def sell_stock(self, request):
        """
        Custom action untuk menjual/mengeluarkan stok.
        Akses: POST /api/inventory/stock/sell/
        """
        product_id = request.data.get('product')
        location_id = request.data.get('location')
        quantity = request.data.get('quantity')
        notes = request.data.get('notes')

        if not all([product_id, location_id, quantity]):
            return Response({"detail": "Product, location, and quantity are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Panggil service sell_stock (pastikan service-nya sudah disesuaikan untuk menerima ID)
            movement = StockService.sell_stock(
                product_id=product_id,
                location_id=location_id,
                quantity=quantity,
                notes=notes
            )
            return Response({"detail": "Stock sold successfully.", "movement_id": movement.id}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='transfer')
    def transfer_stock(self, request):
        """
        Custom action untuk mentransfer stok.
        Akses: POST /api/inventory/stock/transfer/
        """
        product_id = request.data.get('product')
        from_location_id = request.data.get('from_location')
        to_location_id = request.data.get('to_location')
        quantity = request.data.get('quantity')
        notes = request.data.get('notes')

        if not all([product_id, from_location_id, to_location_id, quantity]):
            return Response({"detail": "Product, from_location, to_location, and quantity are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Panggil service transfer_stock (pastikan service-nya sudah disesuaikan untuk menerima ID)
            out_movement, in_movement = StockService.transfer_stock(
                product_id=product_id,
                from_location_id=from_location_id,
                to_location_id=to_location_id,
                quantity=quantity,
                notes=notes
            )
            return Response({"detail": "Stock transferred successfully."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='adjust')
    def adjust_stock(self, request):
        """
        Custom action untuk penyesuaian stok.
        Akses: POST /api/inventory/stock/adjust/
        """
        product_id = request.data.get('product')
        location_id = request.data.get('location')
        quantity_change = request.data.get('quantity_change')
        reason = request.data.get('reason')
        notes = request.data.get('notes')

        if not all([product_id, location_id, quantity_change, reason]):
            return Response({"detail": "Product, location, quantity_change, and reason are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Panggil service adjust_stock (pastikan service-nya sudah disesuaikan untuk menerima ID)
            movement = StockService.adjust_stock(
                product_id=product_id,
                location_id=location_id,
                quantity_change=quantity_change,
                reason=reason,
                notes=notes
            )
            return Response({"detail": "Stock adjusted successfully.", "movement_id": movement.id}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class BillOfMaterialsViewSet(viewsets.ModelViewSet):
    queryset = BillOfMaterials.objects.all()
    serializer_class = BillOfMaterialsSerializer
    permission_classes = [IsAdminOrWarehouse]

    def get_queryset(self):
        queryset = BillOfMaterials.objects.select_related('product').prefetch_related('bom_items__component').all()
        product = self.request.query_params.get('product', None)
        
        if product:
            queryset = queryset.filter(product_id=product)
            
        return queryset.order_by('product__name', 'version')

class BOMItemViewSet(viewsets.ModelViewSet):
    queryset = BOMItem.objects.all()
    serializer_class = BOMItemSerializer
    permission_classes = [IsAdminOrWarehouse]

    def get_queryset(self):
        queryset = BOMItem.objects.select_related('bom', 'component').all()
        bom = self.request.query_params.get('bom', None)
        
        if bom:
            queryset = queryset.filter(bom_id=bom)
            
        return queryset.order_by('bom__product__name', 'component__name')

class AssemblyOrderViewSet(viewsets.ModelViewSet):
    queryset = AssemblyOrder.objects.all()
    serializer_class = AssemblyOrderSerializer
    permission_classes = [IsAdminOrWarehouse]

    def get_queryset(self):
        queryset = AssemblyOrder.objects.select_related('bom__product').prefetch_related('items__component').all()
        bom = self.request.query_params.get('bom', None)
        date_from = self.request.query_params.get('date_from', None)
        date_to = self.request.query_params.get('date_to', None)
        
        if bom:
            queryset = queryset.filter(bom_id=bom)
            
        if date_from:
            queryset = queryset.filter(order_date__gte=date_from)
            
        if date_to:
            queryset = queryset.filter(order_date__lte=date_to)
            
        return queryset.order_by('-order_date')

class AssemblyOrderItemViewSet(viewsets.ModelViewSet):
    queryset = AssemblyOrderItem.objects.all()
    serializer_class = AssemblyOrderItemSerializer
    permission_classes = [IsAdminOrWarehouse]

    def get_queryset(self):
        queryset = AssemblyOrderItem.objects.select_related('assembly_order', 'component').all()
        assembly_order = self.request.query_params.get('assembly_order', None)
        
        if assembly_order:
            queryset = queryset.filter(assembly_order_id=assembly_order)
            
        return queryset.order_by('assembly_order__order_date', 'component__name')
