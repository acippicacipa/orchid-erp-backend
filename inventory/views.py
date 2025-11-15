from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny
from accounts.permissions import IsAdminOrSales
from django.db.models import Q, F, Sum, Subquery, OuterRef, DecimalField, Value, Case, When
from django.db.models.functions import Coalesce
from django_filters.rest_framework import DjangoFilterBackend
from accounts.permissions import IsAdminOrWarehouse
from django.db import transaction, models
from django.shortcuts import get_object_or_404
from django.utils import timezone
from purchasing.models import PurchaseOrder, PurchaseOrderItem
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from .models import (
    MainCategory, SubCategory, Category, Location, Product, Stock, 
    BillOfMaterials, BOMItem, AssemblyOrder, AssemblyOrderItem, StockMovement, GoodsReceipt, GoodsReceiptItem, StockTransfer, StockTransferItem
)
from .serializers import (
    MainCategorySerializer, SubCategorySerializer, CategorySerializer, 
    LocationSerializer, ProductSerializer, StockSerializer,
    BillOfMaterialsSerializer, BOMItemSerializer, 
    AssemblyOrderSerializer, AssemblyOrderItemSerializer, StockMovementSerializer, GoodsReceiptSerializer, CreateGoodsReceiptSerializer, 
    PurchaseOrderForReceiptSerializer, AssemblyOrderForReceiptSerializer, CreateBulkMovementSerializer, InventoryProductSearchSerializer,
    StockTransferSerializer
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

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """
        Mengambil riwayat pergerakan stok dengan saldo awal dan akhir.
        """
        stock_item = self.get_object()
        
        start_date_str = request.query_params.get('start_date', None)
        end_date_str = request.query_params.get('end_date', None)

        # --- 1. HITUNG SALDO AWAL (OPENING BALANCE) ---
        opening_balance = Decimal('0.0') # Default saldo awal adalah 0
        
        # Hanya hitung saldo awal jika start_date diberikan
        if start_date_str:
            try:
                # Pastikan format tanggal valid
                start_date_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
                
                # Ambil semua pergerakan SEBELUM start_date
                opening_balance_query = StockMovement.objects.filter(
                    product=stock_item.product,
                    location=stock_item.location,
                    movement_date__lt=start_date_dt
                )
                
                opening_balance_agg = opening_balance_query.aggregate(total_quantity=Sum('quantity'))
                opening_balance = opening_balance_agg['total_quantity'] or Decimal('0.0')

            except (ValueError, TypeError):
                # Jika format tanggal salah, biarkan opening_balance tetap 0
                pass

        # --- 2. AMBIL PERGERAKAN DALAM RENTANG TANGGAL ---
        movements_query = StockMovement.objects.filter(
            product=stock_item.product,
            location=stock_item.location
        )

        if start_date_str:
            # Gunakan GTE (>=) untuk mencakup transaksi pada start_date
            movements_query = movements_query.filter(movement_date__gte=start_date_str)
            
        if end_date_str:
            try:
                # Tambah 1 hari untuk membuat end_date inklusif
                end_date_dt = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
                movements_query = movements_query.filter(movement_date__lt=end_date_dt)
            except (ValueError, TypeError):
                pass

        # --- 3. HITUNG SALDO AKHIR (CLOSING BALANCE) ---
        # Ambil semua pergerakan dalam periode yang difilter
        movements_in_period = movements_query.order_by('movement_date', 'created_at')
        
        # Jumlahkan kuantitas dari pergerakan dalam periode ini
        movements_in_period_total = movements_in_period.aggregate(
            total_quantity=Sum('quantity')
        )['total_quantity'] or Decimal('0.0')
        
        # Saldo akhir adalah saldo awal + total pergerakan dalam periode
        closing_balance = opening_balance + movements_in_period_total

        # --- 4. SERIALISASI DAN KEMBALIKAN DATA ---
        serializer = StockMovementSerializer(movements_in_period, many=True)
        
        response_data = {
            'opening_balance': opening_balance,
            'closing_balance': closing_balance,
            'movements': serializer.data,
        }
        
        return Response(response_data)

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

    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['product__name', 'product__sku', 'bom_number']
    filterset_fields = ['product', 'is_default']

    def get_queryset(self):
        queryset = BillOfMaterials.objects.select_related('product').prefetch_related('bom_items__component').all()
        
        # Logika filter 'product' yang lama bisa dihapus karena sudah ditangani oleh filterset_fields
        # product = self.request.query_params.get('product', None)
        # if product:
        #     queryset = queryset.filter(product_id=product)
            
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

    @action(detail=True, methods=['get'], url_path='check-availability')
    def check_availability(self, request, pk=None):
        """
        Checks the material availability for a given assembly order without changing its status.
        """
        order = self.get_object()

        # Validasi 1: Pastikan order memiliki BOM
        if not order.bom:
            return Response(
                {'error': 'Assembly Order does not have a Bill of Materials assigned.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validasi 2: Pastikan lokasi produksi sudah ditentukan
        if not order.production_location:
            return Response(
                {'error': 'Production location is not set for this order.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        availability_data = []
        is_fully_available = True
        
        # Ambil semua item dari BOM yang terkait
        bom_items = order.bom.bom_items.all()

        for bom_item in bom_items:
            component = bom_item.component
            required_quantity = bom_item.quantity * order.quantity

            # Cek stok komponen di lokasi produksi
            try:
                stock = Stock.objects.get(
                    product=component,
                    location=order.production_location
                )
                available_quantity = stock.quantity_sellable
            except Stock.DoesNotExist:
                available_quantity = 0

            # Tentukan status ketersediaan
            shortage = required_quantity - available_quantity
            if shortage <= 0:
                status_text = 'Available'
                shortage = 0
            else:
                status_text = 'Shortage'
                is_fully_available = False

            availability_data.append({
                'component_id': component.id,
                'component_name': component.name,
                'component_sku': component.sku,
                'component_color': component.color,
                'required_quantity': required_quantity,
                'available_quantity': available_quantity,
                'shortage': shortage,
                'status': status_text,
            })

        # Siapkan respons
        response_data = {
            'order_id': order.id,
            'order_number': order.order_number,
            'is_fully_available': is_fully_available,
            'components': availability_data,
        }

        return Response(response_data)
    
    @action(detail=True, methods=['post'], url_path='release')
    @transaction.atomic
    def release_order(self, request, pk=None):
        """
        Releases a DRAFT assembly order to be ready for production.
        """
        order = self.get_object()
        if order.status != 'DRAFT':
            return Response(
                {'error': 'Only DRAFT orders can be released.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        if not order.production_location:
            return Response(
                {'error': 'Production location must be set before releasing the order.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        required_items = order.items.all()
        if not required_items.exists() and order.bom:
            # Jika item belum ada, buat dari BOM (sebagai fallback)
            required_items = order.bom.bom_items.all()

        for item in required_items:
            component = item.component
            # Jika dari BOM, quantity perlu dikalikan. Jika dari AssemblyOrderItem, sudah final.
            required_quantity = item.quantity if hasattr(item, 'assembly_order') else item.quantity * order.quantity

            try:
                # Ambil record stok untuk komponen ini di lokasi produksi
                stock = Stock.objects.select_for_update().get(
                    product=component,
                    location=order.production_location
                )

                # Cek apakah stok yang bisa dijual mencukupi
                if stock.quantity_sellable < required_quantity:
                    # Jika tidak cukup, batalkan seluruh transaksi
                    raise Exception(f"Insufficient stock for {component.name}. Required: {required_quantity}, Available: {stock.quantity_sellable}")

                # 2. Pindahkan kuantitas dari sellable ke allocated
                stock.quantity_sellable -= required_quantity
                stock.quantity_allocated += required_quantity
                stock.save()

            except Stock.DoesNotExist:
                # Jika record stok tidak ada sama sekali, berarti stok 0
                raise Exception(f"Stock record for component {component.name} not found at location {order.production_location.name}.")
            except Exception as e:
                # Tangkap error dari pengecekan stok dan kirim sebagai respons
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        order.status = 'RELEASED'
        order.save()
        
        serializer = self.get_serializer(order)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='start-production')
    def start_production(self, request, pk=None):
        """
        Starts production for a RELEASED assembly order.
        """
        order = self.get_object()
        if order.status != 'RELEASED':
            return Response(
                {'error': 'Only RELEASED orders can be started.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        order.status = 'IN_PROGRESS'
        order.actual_start_date = timezone.now() # Pastikan timezone diimpor
        order.save()
        
        serializer = self.get_serializer(order)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='report-production')
    def report_production(self, request, pk=None):
        
        order = self.get_object()

        # Validasi 1: Hanya order 'IN_PROGRESS' yang bisa dilaporkan hasilnya
        if order.status != 'IN_PROGRESS':
            return Response(
                {'error': 'Production can only be reported for IN_PROGRESS orders.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validasi 2: Ambil kuantitas dari request body
        try:
            quantity_produced_input = Decimal(request.data.get('quantity_produced', '0'))
            if quantity_produced_input <= 0:
                raise ValueError("Quantity produced must be a positive number.")
        except (ValueError, InvalidOperation): # Tangkap juga InvalidOperation dari Decimal
            return Response(
                {'error': 'Invalid or missing "quantity_produced" in request.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validasi tambahan: Pastikan order memiliki BOM
        if not order.bom:
            return Response({'error': 'Cannot report production without a BOM.'}, status=status.HTTP_400_BAD_REQUEST)
       
        bom_items = order.bom.bom_items.all()
        production_location = order.production_location
        
        # Buat daftar untuk menyimpan kebutuhan dan stok yang akan di-update
        component_updates = []

        for bom_item in bom_items:
            component = bom_item.component
            quantity_consumed = bom_item.quantity * quantity_produced_input

            try:
                component_stock = Stock.objects.get(product=component, location=production_location)
                if component_stock.quantity_sellable < quantity_consumed:
                    # Jika stok tidak cukup, langsung kirim error dan hentikan proses
                    return Response(
                        {'error': f"Insufficient stock for {component.sku}. Required: {quantity_consumed}, Available: {component_stock.quantity_sellable}."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                component_updates.append({'stock': component_stock, 'consumed': quantity_consumed})
            except Stock.DoesNotExist:
                # Jika komponen tidak ada sama sekali, langsung kirim error
                return Response(
                    {'error': f"Component {component.sku} not found at location {production_location.name}."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Gunakan transaction.atomic untuk memastikan semua operasi berhasil atau tidak sama sekali
        with transaction.atomic():

            order.quantity_produced += quantity_produced_input
            
            if order.quantity_produced >= order.quantity:
                order.status = 'COMPLETED'
                order.actual_completion_date = timezone.now()
            order.save()

            for update in component_updates:
                component_stock = update['stock']
                quantity_consumed = update['consumed']
                
                component_stock.quantity_on_hand -= quantity_consumed
                component_stock.quantity_sellable -= quantity_consumed
                component_stock.save()

                StockMovement.objects.create(
                    product=component_stock.product, location=production_location, movement_type='ASSEMBLY',
                    quantity=-quantity_consumed, unit_cost=component_stock.average_cost,
                    reference_number=order.order_number, reference_type='ASSEMBLY_ORDER',
                    notes=f'Component for Assembly Order {order.order_number}', user=request.user
                )

        serializer = self.get_serializer(order)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='complete')
    @transaction.atomic
    def complete_order(self, request, pk=None):
        """
        Marks an IN_PROGRESS assembly order as COMPLETED.
        """
        order = self.get_object()
        if order.status != 'IN_PROGRESS':
            return Response(
                {'error': 'Only IN_PROGRESS orders can be completed.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        unproduced_quantity = order.quantity - order.quantity_produced

        # 2. Hanya jalankan logika jika ada selisih (jika produksi kurang dari rencana)
        if unproduced_quantity > 0:
            required_items = order.items.all()
            if not required_items.exists() and order.bom:
                required_items = order.bom.bom_items.all()

            for item in required_items:
                component = item.component
                
                # Hitung berapa banyak komponen yang tidak terpakai
                # Jika dari BOM, quantity per produk jadi. Jika dari AssemblyOrderItem, sudah total.
                # Kita asumsikan item sudah di AssemblyOrderItem, jadi quantity sudah total.
                # Untuk mendapatkan per unit, kita bagi dengan total quantity.
                qty_per_product = item.quantity / order.quantity
                unused_component_qty = qty_per_product * unproduced_quantity

                if unused_component_qty > 0:
                    try:
                        stock = Stock.objects.select_for_update().get(
                            product=component,
                            location=order.production_location
                        )
                        
                        # Pastikan kita tidak mengembalikan lebih dari yang dialokasikan
                        # Ini sebagai pengaman jika ada anomali data
                        deallocate_qty = min(unused_component_qty, stock.quantity_allocated)

                        # 3. Kembalikan stok dari allocated ke sellable
                        stock.quantity_allocated -= deallocate_qty
                        stock.quantity_sellable += deallocate_qty
                        stock.save()

                    except Stock.DoesNotExist:
                        # Seharusnya tidak terjadi jika alokasi berjalan benar
                        print(f"WARNING: Stock record for {component.name} not found during completion of AO {order.order_number}.")
                        pass
        
        order.status = 'COMPLETED'
        order.actual_completion_date = timezone.now()
        order.save()
        
        serializer = self.get_serializer(order)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='cancel')
    @transaction.atomic
    def cancel_order(self, request, pk=None):
        """
        Cancels an assembly order that is not yet completed.
        """
        order = self.get_object()
        original_status = order.status
        if original_status in ['COMPLETED', 'CANCELLED']:
            return Response(
                {'error': f'A {order.status} order cannot be cancelled.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        if original_status in ['RELEASED', 'IN_PROGRESS']:
            required_items = order.items.all()
            for item in required_items:
                component = item.component
                required_quantity = item.quantity

                try:
                    stock = Stock.objects.select_for_update().get(
                        product=component,
                        location=order.production_location
                    )
                    
                    # Kembalikan kuantitas dari allocated ke sellable
                    stock.quantity_allocated -= required_quantity
                    stock.quantity_sellable += required_quantity
                    stock.save()

                except Stock.DoesNotExist:
                    # Ini seharusnya tidak terjadi, tapi sebagai pengaman, log error
                    # Anda bisa menggunakan logging library Python di sini
                    print(f"WARNING: Stock record for {component.name} not found during cancellation of AO {order.order_number}.")
                    pass # Lanjutkan proses meskipun ada anomali
        
        order.status = 'CANCELLED'
        order.save()
        
        serializer = self.get_serializer(order)
        return Response(serializer.data)

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
    filter_backends = [filters.SearchFilter, DjangoFilterBackend] # DjangoFilterBackend jika Anda juga filter by field
    search_fields = ['reference_number', 'product__name', 'product__sku']
    filterset_fields = ['movement_type', 'location', 'product']

    def get_queryset(self):
        """
        Filter queryset berdasarkan query params.
        Contoh: /api/inventory/stock-movements/?product=1&location=2
        """
        queryset = super().get_queryset()

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

    @action(detail=False, methods=['post'], url_path='create_bulk')
    @transaction.atomic
    def create_bulk_movement(self, request):
        """
        Membuat beberapa stock movement sekaligus dari satu request.
        Menangani logika untuk TRANSFER, ADJUSTMENT, DAMAGE, dll.
        """
        serializer = CreateBulkMovementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        movement_type = data['movement_type']
        from_location = data['location']
        to_location = data.get('to_location')
        items = data['items']
        
        reference_number = data.get('reference_number')
        if movement_type == 'TRANSFER' and not reference_number:
            # Buat nomor referensi otomatis untuk transfer
            today_str = timezone.now().strftime('%Y%m%d')
            prefix = f"TRF-{today_str}-"
            last_movement = StockMovement.objects.filter(
                reference_number__startswith=prefix
            ).order_by('-reference_number').first()
            
            if last_movement:
                try:
                    last_seq = int(last_movement.reference_number.split('-')[-1])
                    new_seq = last_seq + 1
                except (ValueError, IndexError):
                    new_seq = 1
            else:
                new_seq = 1
            
            reference_number = f"{prefix}{new_seq:04d}"

        created_movements = []

        for item_data in items:
            product = item_data['product']
            quantity = item_data['quantity']
            
            # Ambil cost dari produk, default 0 jika tidak ada
            unit_cost = product.cost_price or Decimal('0.00')

            if movement_type == 'TRANSFER':
                # Untuk transfer, buat dua movement: satu keluar, satu masuk
                
                # 1. Movement KELUAR dari `from_location`
                out_movement = StockMovement.objects.create(
                    product=product,
                    location=from_location,
                    movement_type=movement_type,
                    quantity=-abs(quantity), # Pastikan negatif
                    unit_cost=unit_cost,
                    notes=data.get('notes', f"Transfer to {to_location.name}"),
                    reference_number=reference_number,
                    user=request.user
                )
                created_movements.append(out_movement)

                # 2. Movement MASUK ke `to_location`
                in_movement = StockMovement.objects.create(
                    product=product,
                    location=to_location,
                    movement_type=movement_type,
                    quantity=abs(quantity), # Pastikan positif
                    unit_cost=unit_cost,
                    notes=data.get('notes', f"Transfer from {from_location.name}"),
                    reference_number=reference_number,
                    user=request.user
                )
                created_movements.append(in_movement)

            else: # Untuk tipe lain (ADJUSTMENT, DAMAGE, RECEIPT)
                # Tentukan apakah kuantitas harus positif atau negatif
                if movement_type in ['DAMAGE', 'SALE']:
                    # Jika barang rusak atau dijual, kuantitasnya mengurangi stok
                    final_quantity = -abs(quantity)
                else:
                    # Jika adjustment positif atau receipt, kuantitas menambah stok
                    final_quantity = abs(quantity)

                movement = StockMovement.objects.create(
                    product=product,
                    location=from_location,
                    movement_type=movement_type,
                    quantity=final_quantity,
                    unit_cost=unit_cost,
                    notes=data.get('notes'),
                    reference_number=reference_number,
                    user=request.user
                )
                created_movements.append(movement)

        # Serialize data yang baru dibuat untuk respons
        response_serializer = StockMovementSerializer(created_movements, many=True)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['get'], url_path='transfer-history')
    def transfer_history(self, request):
        """
        Mengembalikan daftar riwayat transfer yang sudah dikelompokkan per nomor referensi.
        """
        search_query = request.query_params.get('search', None)

        # Ambil semua movement transfer, urutkan berdasarkan referensi dan tanggal
        movements = StockMovement.objects.filter(movement_type='TRANSFER').order_by('-movement_date', 'reference_number')

        if search_query:
            movements = movements.filter(
                Q(reference_number__icontains=search_query) |
                Q(notes__icontains=search_query) |
                Q(product__name__icontains=search_query)
            ).distinct()

        # Gunakan pagination dari DRF
        paginator = self.pagination_class()
        paginated_movements = paginator.paginate_queryset(movements, request)

        # Kelompokkan hasil dari halaman saat ini
        grouped_transfers = {}
        for mov in paginated_movements:
            ref = mov.reference_number
            if ref not in grouped_transfers:
                grouped_transfers[ref] = {
                    'reference_number': ref,
                    'date': mov.movement_date,
                    'user': mov.user.username if mov.user else 'System',
                    'notes': mov.notes,
                    'from_location': 'N/A',
                    'to_location': 'N/A',
                    'items': []
                }
            
            # Tentukan lokasi asal dan tujuan
            if mov.quantity < 0:
                grouped_transfers[ref]['from_location'] = mov.location.name
            else:
                grouped_transfers[ref]['to_location'] = mov.location.name
            
            # Cek agar tidak ada duplikasi item (jika satu item muncul dua kali)
            if not any(item['product_id'] == mov.product.id for item in grouped_transfers[ref]['items']):
                grouped_transfers[ref]['items'].append({
                    'product_id': mov.product.id,
                    'product_name': mov.product.name,
                    'product_sku': mov.product.sku,
                    'quantity': abs(mov.quantity)
                })

        # Kembalikan hasil dalam format paginasi DRF
        return paginator.get_paginated_response(list(grouped_transfers.values()))

class GoodsReceiptViewSet(viewsets.ModelViewSet):
    queryset = GoodsReceipt.objects.all().select_related(
        'purchase_order', 'assembly_order', 'supplier', 'location', 'received_by'
    )
    serializer_class = GoodsReceiptSerializer
    permission_classes = [AllowAny]

    filter_backends = [filters.SearchFilter]
    search_fields = [
        'receipt_number', 
        'purchase_order__order_number', 
        'assembly_order__order_number',
        'supplier__name'
    ]
    
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

    @action(detail=False, methods=['get'])
    def available_assembly_orders(self, request):
        """
        Menyediakan daftar Assembly Orders yang memiliki barang jadi yang siap diterima.
        """
        # Kita cari AO yang statusnya IN_PROGRESS atau COMPLETED
        # dan jumlah yang diproduksi > 0
        assembly_orders = AssemblyOrder.objects.filter(
            Q(status__in=['IN_PROGRESS', 'COMPLETED']),
            Q(quantity_produced__gt=0)
        ).select_related('product')

        # Kita bisa filter lebih lanjut untuk hanya menampilkan yang masih punya sisa untuk diterima
        # (Ini akan menggunakan SerializerMethodField yang kita buat)
        
        serializer = AssemblyOrderForReceiptSerializer(assembly_orders, many=True)
        
        # Filter hasil serialisasi di Python untuk hanya menyertakan yang quantity_remaining > 0
        available_orders = [order for order in serializer.data if order['quantity_remaining'] > 0]
        
        return Response(available_orders)
    
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
                
                if goods_receipt.assembly_order:
                    ao = goods_receipt.assembly_order
                    # Hitung total yang sudah diterima untuk AO ini
                    total_received = ao.goods_receipts.filter(status='CONFIRMED').aggregate(
                        total=models.Sum('items__quantity_received')
                    )['total'] or 0
                    
                    # Jika total yang diterima >= total yang diproduksi, AO bisa dianggap selesai diterima
                    if total_received >= ao.quantity_produced:
                        # Di sini Anda bisa menambahkan logika tambahan, misal mengubah status custom di AO
                        pass

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

class ProductSearchViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for product search in sales orders
    """
    queryset = Product.objects.filter(is_active=True)
    serializer_class = InventoryProductSearchSerializer
    permission_classes = [IsAdminOrSales]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'sku']

    def get_queryset(self):
        """
        Fungsi ini sekarang akan dipanggil oleh action 'search' kita.
        Ia akan menganotasi queryset dengan stok yang benar.
        """
        queryset = super().get_queryset()
        location_id_str = self.request.query_params.get('location_id', None)

        if location_id_str:
            try:
                location_id = int(location_id_str)
                stock_subquery = Stock.objects.filter(
                    product=OuterRef('pk'),
                    location_id=location_id
                ).values('quantity_on_hand')[:1]

                queryset = queryset.annotate(
                    current_stock=Coalesce(
                        Subquery(stock_subquery, output_field=DecimalField()),
                        Value(Decimal('0.00')),
                        output_field=DecimalField()
                    )
                )
            except (ValueError, TypeError):
                queryset = queryset.annotate(current_stock=Value(Decimal('0.00'), output_field=DecimalField()))
        else:
            queryset = queryset.annotate(current_stock=Value(Decimal('0.00'), output_field=DecimalField()))
            
        return queryset

    @action(detail=False, methods=['get'])
    def search(self, request):
        """
        Action pencarian yang sekarang menggunakan queryset utama dan filter backend.
        """
        queryset = self.get_queryset()
        
        # filter_queryset akan otomatis membaca 'search' dari request.query_params
        filtered_queryset = self.filter_queryset(queryset)

        paginated_queryset = filtered_queryset[:20]

        serializer = self.get_serializer(paginated_queryset, many=True)
        
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], url_path='calculate-price')
    def calculate_price(self, request, pk=None):
        """
        Calculates the price and discount for a product based on customer and quantity.
        Expects 'customer_id' and 'quantity' as query parameters.
        """
        product = self.get_object()
        
        customer_id = request.query_params.get('customer_id')
        quantity_str = request.query_params.get('quantity', '1')

        if not customer_id:
            return Response(
                {'error': 'customer_id is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            customer = Customer.objects.get(pk=customer_id)
        except Customer.DoesNotExist:
            return Response({'error': f"Customer with ID {customer_id} not found"}, status=status.HTTP_404_NOT_FOUND)
        except (ValueError, TypeError):
             return Response({'error': 'Invalid customer_id format'}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Validasi Kuantitas secara terpisah
        try:
            quantity = Decimal(quantity_str)
            if quantity <= 0:
                raise InvalidOperation("Quantity must be positive.")
        except InvalidOperation as e: # Tangkap error konversi Decimal secara spesifik
            return Response({'error': f"Invalid quantity: {e}"}, status=status.HTTP_400_BAD_REQUEST)
            
        # Jika semua validasi lolos, panggil service
        pricing_data = PricingService.get_price_and_discount(customer, product, quantity)
        
        return Response(pricing_data)

class StockTransferViewSet(viewsets.ModelViewSet):
    queryset = StockTransfer.objects.prefetch_related('items', 'items__product', 'created_by').all().order_by('-created_at')
    serializer_class = StockTransferSerializer
    permission_classes = [IsAuthenticated] # Pastikan hanya user terautentikasi yang bisa akses

    def perform_create(self, serializer):
        """
        Secara otomatis mengatur 'created_by' saat membuat transfer baru.
        """
        serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        """
        Override metode create untuk memastikan data diambil dari request.data.
        """
        # 1. Ambil data dari body request (JSON)
        data = request.data
        
        # 2. Inisialisasi serializer dengan data dari body
        serializer = self.get_serializer(data=data)
        
        # 3. Validasi data
        serializer.is_valid(raise_exception=True)
        
        # 4. Panggil perform_create (yang akan mengisi 'created_by') dan simpan
        self.perform_create(serializer)
        
        # 5. Siapkan header dan kembalikan respons sukses
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=['post'], url_path='send') # Ganti nama dari 'dispatch' menjadi 'send'
    def send(self, request, pk=None):
        """
        Action untuk mengirim transfer. Mengubah status ke IN_TRANSIT dan
        membuat StockMovement negatif (keluar) dari lokasi asal.
        """
        transfer = self.get_object()
        if transfer.status != 'PENDING':
            return Response({'detail': f'Transfer is already {transfer.status}, cannot dispatch.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            movements_to_create = []
            for item in transfer.items.all():
                # Validasi: Pastikan stok di lokasi asal mencukupi
                stock, created = Stock.objects.get_or_create(
                    product=item.product,
                    location=transfer.from_location,
                    defaults={'quantity_on_hand': Decimal('0.00')}
                )
                if stock.quantity_on_hand < item.quantity:
                    raise serializers.ValidationError(
                        f"Insufficient stock for {item.product.name} at {transfer.from_location.name}. "
                        f"Required: {item.quantity}, Available: {stock.quantity_on_hand}."
                    )

                movements_to_create.append(
                    StockMovement(
                        product=item.product,
                        location=transfer.from_location,
                        movement_type='TRANSFER_OUT',
                        quantity=-item.quantity,  # Kuantitas negatif
                        reference_number=transfer.transfer_number,
                        reference_type='STOCK_TRANSFER',
                        user=request.user,
                        notes=f"Dispatch to {transfer.to_location.name}"
                    )
                )
            
            for movement_data in movements_to_create:
                movement_data.save()
            
            # Update status transfer
            transfer.status = 'IN_TRANSIT'
            transfer.save(update_fields=['status', 'updated_at'])
            
        serializer = self.get_serializer(transfer)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='receive')
    def receive(self, request, pk=None):
        """
        Action untuk menerima transfer. Mengubah status ke COMPLETED dan
        membuat StockMovement positif (masuk) ke lokasi tujuan.
        """
        transfer = self.get_object()
        if transfer.status != 'IN_TRANSIT':
            return Response({'detail': f'Transfer is not IN_TRANSIT, cannot receive.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            movements_to_create = []
            for item in transfer.items.all():
                movements_to_create.append(
                    StockMovement(
                        product=item.product,
                        location=transfer.to_location,
                        movement_type='TRANSFER_IN',
                        quantity=item.quantity,  # Kuantitas positif
                        reference_number=transfer.transfer_number,
                        reference_type='STOCK_TRANSFER',
                        user=request.user,
                        notes=f"Receipt from {transfer.from_location.name}"
                    )
                )
            
            # Buat semua movement. Sinyal post_save akan otomatis mengupdate stok.
            for movement_data in movements_to_create:
                movement_data.save()
            
            # Update status transfer
            transfer.status = 'COMPLETED'
            transfer.save(update_fields=['status', 'updated_at'])
            
        serializer = self.get_serializer(transfer)
        return Response(serializer.data, status=status.HTTP_200_OK)