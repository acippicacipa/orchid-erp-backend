from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.shortcuts import get_object_or_404

from .models import GoodsReceipt, GoodsReceiptItem, StockMovement, Stock, Location
from .serializers import (
    GoodsReceiptSerializer, CreateGoodsReceiptSerializer, 
    PurchaseOrderForReceiptSerializer, StockMovementSerializer
)
from purchasing.models import PurchaseOrder, PurchaseOrderItem

class GoodsReceiptViewSet(viewsets.ModelViewSet):
    queryset = GoodsReceipt.objects.all()
    serializer_class = GoodsReceiptSerializer
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
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
        """Confirm goods receipt and update stock"""
        goods_receipt = self.get_object()
        
        if goods_receipt.status != 'DRAFT':
            return Response(
                {'error': 'Only draft receipts can be confirmed'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                # Update goods receipt status
                goods_receipt.status = 'CONFIRMED'
                goods_receipt.save()
                
                # Process each item to update stock
                for item in goods_receipt.items.all():
                    # Get or create stock record
                    default_location = item.location or Location.objects.filter(
                        is_active=True, 
                        is_purchasable_location=True
                    ).first()
                    
                    if not default_location:
                        raise Exception("No suitable location found for stock update")
                    
                    stock, created = Stock.objects.get_or_create(
                        product=item.product,
                        location=default_location,
                        defaults={
                            'quantity_on_hand': 0,
                            'quantity_sellable': 0,
                            'average_cost': item.unit_price,
                            'last_cost': item.unit_price,
                        }
                    )
                    
                    # Update stock quantities
                    old_quantity = stock.quantity_on_hand
                    stock.quantity_on_hand += item.quantity_received
                    stock.quantity_sellable += item.quantity_received
                    stock.last_cost = item.unit_price
                    stock.last_received_date = goods_receipt.receipt_date
                    
                    # Update average cost using weighted average
                    if old_quantity > 0:
                        total_value = old_quantity * stock.average_cost + item.quantity_received * item.unit_price
                        stock.average_cost = total_value / stock.quantity_on_hand
                    else:
                        stock.average_cost = item.unit_price
                    
                    stock.save()
                    
                    # Create stock movement record
                    StockMovement.objects.create(
                        product=item.product,
                        location=default_location,
                        movement_type='RECEIPT',
                        quantity=item.quantity_received,
                        unit_cost=item.unit_price,
                        reference_number=goods_receipt.receipt_number,
                        reference_type='GOODS_RECEIPT',
                        notes=f"Goods receipt from PO {goods_receipt.purchase_order.order_number}",
                        user=request.user,
                    )
                
                # Check if purchase order is fully received
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
