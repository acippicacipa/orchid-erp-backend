from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny
from django.db.models import Q, F
from accounts.permissions import IsAdminOrWarehouse
from django.db import transaction
from django.shortcuts import get_object_or_404
from purchasing.models import PurchaseOrder, PurchaseOrderItem
from .models import (
    MainCategory, SubCategory, Category, Location, Product, Stock, 
    BillOfMaterials, BOMItem, AssemblyOrder, AssemblyOrderItem, StockMovement, GoodsReceipt, GoodsReceiptItem
)
from .serializers import (
    MainCategorySerializer, SubCategorySerializer, CategorySerializer, 
    LocationSerializer, ProductSerializer, StockSerializer,
    BillOfMaterialsSerializer, BOMItemSerializer, 
    AssemblyOrderSerializer, AssemblyOrderItemSerializer, StockMovementSerializer, GoodsReceiptSerializer, CreateGoodsReceiptSerializer, 
    PurchaseOrderForReceiptSerializer
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
        search_query = self.request.query_params.get('search', None) # <-- Parameter baru
        
        if product:
            queryset = queryset.filter(product_id=product)
            
        if location:
            queryset = queryset.filter(location_id=location)
            
        if low_stock and low_stock.lower() == 'true':
            # Filter for products where current stock is below minimum level
            queryset = queryset.filter(
                quantity_on_hand__lt=F('product__minimum_stock_level')
            )
            
        if search_query:
            # Gunakan Q object untuk melakukan pencarian OR pada beberapa field
            queryset = queryset.filter(
                Q(product__name__icontains=search_query) | 
                Q(product__sku__icontains=search_query)
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
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = BillOfMaterials.objects.select_related('product').prefetch_related('bom_items__component').all()
        product = self.request.query_params.get('product', None)
        
        if product:
            queryset = queryset.filter(product_id=product)
            
        return queryset.order_by('product__name', 'version')
    
    def perform_create(self, serializer):
        """
        Secara otomatis mengatur 'created_by' saat membuat objek baru.
        """
        # self.request.user adalah objek pengguna yang sedang login,
        # didapatkan dari token autentikasi.
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        """
        Secara otomatis mengatur 'updated_by' saat memperbarui objek.
        """
        # Kita juga bisa mengatur created_by di sini jika field tersebut kosong,
        # sebagai jaring pengaman untuk data lama.
        if hasattr(serializer.instance, 'created_by') and not serializer.instance.created_by:
            serializer.save(updated_by=self.request.user, created_by=self.request.user)
        else:
            serializer.save(updated_by=self.request.user)

class BOMItemViewSet(viewsets.ModelViewSet):
    queryset = BOMItem.objects.all()
    serializer_class = BOMItemSerializer
    permission_classes = [AllowAny]

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

class StockMovementViewSet(viewsets.ModelViewSet):
    """
    API endpoint untuk melihat dan mengelola pergerakan stok.
    """
    queryset = StockMovement.objects.all()
    serializer_class = StockMovementSerializer
    permission_classes = [IsAdminOrWarehouse] # Sesuaikan dengan izin yang Anda inginkan

    def get_queryset(self):
        """
        Filter queryset berdasarkan query params.
        Contoh: /api/inventory/stock-movements/?product=1&location=2
        """
        queryset = StockMovement.objects.select_related(
            'product', 'location', 'user', 'created_by'
        ).all()

        # Ambil parameter dari URL
        product_id = self.request.query_params.get('product', None)
        location_id = self.request.query_params.get('location', None)
        movement_type = self.request.query_params.get('movement_type', None)
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)

        if product_id:
            queryset = queryset.filter(product_id=product_id)
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        if movement_type:
            queryset = queryset.filter(movement_type=movement_type)
        if start_date:
            queryset = queryset.filter(movement_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(movement_date__lte=end_date)
            
        return queryset.order_by('-movement_date')

    def perform_create(self, serializer):
        """
        Secara otomatis mengatur 'created_by' dan 'user' saat membuat objek baru.
        """
        serializer.save(
            created_by=self.request.user,
            user=self.request.user # Asumsikan pengguna yang membuat adalah yang melakukan aksi
        )

    def perform_update(self, serializer):
        """
        Secara otomatis mengatur 'updated_by' saat memperbarui objek.
        """
        serializer.save(updated_by=self.request.user)

class GoodsReceiptViewSet(viewsets.ModelViewSet):
    queryset = GoodsReceipt.objects.all()
    serializer_class = GoodsReceiptSerializer
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        # Gunakan serializer yang sudah dimodifikasi
        if self.action in ['create', 'update']:
            return CreateGoodsReceiptSerializer
        return GoodsReceiptSerializer
    
    @action(detail=False, methods=['get'])
    def available_purchase_orders(self, request):
        """Get purchase orders that can be received"""
        # Get confirmed purchase orders that haven't been fully received
        purchase_orders = PurchaseOrder.objects.filter(
            status__in=['CONFIRMED', 'PENDING']
        ).prefetch_related('items__product')
        
        serializer = PurchaseOrderForReceiptSerializer(purchase_orders, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def create_from_purchase_order(self, request):
        """Create goods receipt from purchase order"""
        purchase_order_id = request.data.get('purchase_order_id')
        items_data = request.data.get('items', [])
        
        if not purchase_order_id:
            return Response(
                {'error': 'Purchase order ID is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        purchase_order = get_object_or_404(PurchaseOrder, id=purchase_order_id)
        
        try:
            with transaction.atomic():
                # Create goods receipt
                goods_receipt = GoodsReceipt.objects.create(
                    purchase_order=purchase_order,
                    received_by=request.user,
                    notes=request.data.get('notes', ''),
                    status='DRAFT'
                )
                
                # Create goods receipt items
                for item_data in items_data:
                    po_item_id = item_data.get('purchase_order_item_id')
                    quantity_received = item_data.get('quantity_received', 0)
                    location_id = item_data.get('location_id')
                    
                    if not po_item_id or quantity_received <= 0:
                        continue
                    
                    po_item = get_object_or_404(PurchaseOrderItem, id=po_item_id)
                    location = None
                    if location_id:
                        location = get_object_or_404(Location, id=location_id)
                    
                    GoodsReceiptItem.objects.create(
                        goods_receipt=goods_receipt,
                        purchase_order_item=po_item,
                        product=po_item.product,
                        quantity_ordered=po_item.quantity,
                        quantity_received=quantity_received,
                        unit_price=po_item.unit_price,
                        location=location,
                        batch_number=item_data.get('batch_number', ''),
                        expiry_date=item_data.get('expiry_date'),
                        notes=item_data.get('notes', '')
                    )
                
                serializer = GoodsReceiptSerializer(goods_receipt)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
                
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def confirm_receipt(self, request, pk=None):
        goods_receipt = self.get_object()
        
        if goods_receipt.status != 'DRAFT':
            return Response({'error': 'Hanya receipt berstatus DRAFT yang bisa dikonfirmasi'}, status=status.HTTP_400_BAD_REQUEST)
        
        # VALIDASI: Pastikan lokasi sudah diisi
        if not goods_receipt.location:
            return Response({'error': 'Lokasi penerimaan harus ditentukan sebelum konfirmasi'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                goods_receipt.status = 'CONFIRMED'
                goods_receipt.save()
                
                for item in goods_receipt.items.all():
                    # **FIX**: Gunakan lokasi dari parent (GoodsReceipt)
                    stock_location = goods_receipt.location
                    
                    stock, created = Stock.objects.get_or_create(
                        product=item.product,
                        location=stock_location,
                        defaults={
                            'quantity_on_hand': 0,
                            'quantity_sellable': 0,
                            'average_cost': item.unit_price or 0,
                            'last_cost': item.unit_price or 0,
                        }
                    )
                    
                    # Update stock quantities
                    unit_price = item.unit_price or 0
                    old_quantity = stock.quantity_on_hand
                    stock.quantity_on_hand += item.quantity_received
                    stock.quantity_sellable += item.quantity_received
                    stock.last_cost = unit_price
                    stock.last_received_date = goods_receipt.receipt_date
                    
                    # Update average cost using weighted average
                    if old_quantity > 0 and stock.quantity_on_hand > 0:
                        total_value = (old_quantity * stock.average_cost) + (item.quantity_received * unit_price)
                        stock.average_cost = total_value / stock.quantity_on_hand
                    else:
                        stock.average_cost = unit_price
                    
                    stock.save()
                    
                    # Create stock movement record
                    StockMovement.objects.create(
                        product=item.product,
                        location=stock_location,
                        movement_type='RECEIPT',
                        quantity=item.quantity_received,
                        unit_cost=unit_price,
                        reference_number=goods_receipt.receipt_number,
                        reference_type='GOODS_RECEIPT',
                        notes=f"Goods receipt from PO {goods_receipt.purchase_order.order_number}" if goods_receipt.purchase_order else "Manual goods receipt",
                        user=request.user,
                    )
                
                # Check if purchase order is fully received
                if goods_receipt.purchase_order:
                    po = goods_receipt.purchase_order
                    all_items_received = True
                    for po_item in po.items.all():
                        total_received = sum(
                            gr_item.quantity_received 
                            for gr_item in po_item.goodsreceiptitem_set.all()
                        )
                        if total_received < po_item.quantity:
                            all_items_received = False
                            break
                    
                    if all_items_received:
                        po.status = 'RECEIVED'
                        po.save()
                
                serializer = GoodsReceiptSerializer(goods_receipt)
                return Response(serializer.data)
                
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['get'])
    def stock_movements(self, request, pk=None):
        """Get stock movements related to this goods receipt"""
        goods_receipt = self.get_object()
        movements = StockMovement.objects.filter(
            reference_number=goods_receipt.receipt_number,
            reference_type='GOODS_RECEIPT'
        )
        serializer = StockMovementSerializer(movements, many=True)
        return Response(serializer.data)
