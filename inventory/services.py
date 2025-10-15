"""
Inventory Services for Real-time Stock Tracking
"""

from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from .models import Product, Stock, StockMovement, Location
import logging

logger = logging.getLogger(__name__)


class StockService:
    """Service for managing stock operations and real-time tracking"""
    
    @staticmethod
    def get_or_create_stock(product, location):
        """Get or create stock record for product at location"""
        stock, created = Stock.objects.get_or_create(
            product=product,
            location=location,
            defaults={
                'quantity_on_hand': Decimal('0.00'),
                'quantity_sellable': Decimal('0.00'),
                'quantity_non_sellable': Decimal('0.00'),
                'quantity_reserved': Decimal('0.00'),
                'quantity_allocated': Decimal('0.00'),
                'minimum_stock_level': product.minimum_stock_level,
                'reorder_point': product.reorder_point,
            }
        )
        return stock
    
    @staticmethod
    @transaction.atomic
    def receive_stock(product, location, quantity, unit_cost=None, 
                     reference_type=None, reference_id=None, reference_number=None,
                     lot_number=None, expiry_date=None, notes=None):
        """
        Receive stock into inventory
        """
        try:
            # Get or create stock record
            stock = StockService.get_or_create_stock(product, location)
            
            # Default unit cost
            if unit_cost is None:
                unit_cost = product.cost_price or Decimal('0.00')
            
            # Create stock movement
            movement = StockMovement.objects.create(
                product=product,
                location=location,
                movement_type='RECEIPT',
                quantity=quantity,
                quantity_sellable=quantity,  # Default to sellable
                quantity_non_sellable=Decimal('0.00'),
                unit_cost=unit_cost,
                reference_type=reference_type,
                reference_id=reference_id,
                reference_number=reference_number,
                lot_number=lot_number,
                expiry_date=expiry_date,
                notes=notes,
                status='COMPLETED'
            )
            
            # Update stock quantities
            stock.quantity_sellable += quantity
            stock.quantity_on_hand += quantity
            
            # Update cost information
            if stock.quantity_on_hand > 0:
                total_value = (stock.average_cost * (stock.quantity_on_hand - quantity)) + (unit_cost * quantity)
                stock.average_cost = total_value / stock.quantity_on_hand
            else:
                stock.average_cost = unit_cost
            
            stock.last_cost = unit_cost
            stock.last_received_date = timezone.now()
            stock.save()
            
            logger.info(f"Received {quantity} units of {product.name} at {location.name}")
            return movement
            
        except Exception as e:
            logger.error(f"Error receiving stock: {str(e)}")
            raise
    
    @staticmethod
    @transaction.atomic
    def sell_stock(product, location, quantity, unit_price=None,
                  reference_type=None, reference_id=None, reference_number=None,
                  notes=None):
        """
        Sell stock from inventory
        """
        try:
            # Get stock record
            stock = Stock.objects.get(product=product, location=location)
            
            # Check availability
            if stock.quantity_available < quantity:
                raise ValueError(f"Insufficient sellable stock. Available: {stock.quantity_available}, Requested: {quantity}")
            
            # Create stock movement
            movement = StockMovement.objects.create(
                product=product,
                location=location,
                movement_type='SALE',
                quantity=-quantity,  # Negative for outbound
                quantity_sellable=-quantity,
                quantity_non_sellable=Decimal('0.00'),
                unit_cost=stock.average_cost,
                reference_type=reference_type,
                reference_id=reference_id,
                reference_number=reference_number,
                notes=notes,
                status='COMPLETED'
            )
            
            # Update stock quantities
            stock.quantity_sellable -= quantity
            stock.quantity_on_hand -= quantity
            stock.last_sold_date = timezone.now()
            stock.save()
            
            logger.info(f"Sold {quantity} units of {product.name} from {location.name}")
            return movement
            
        except Stock.DoesNotExist:
            raise ValueError(f"No stock found for {product.name} at {location.name}")
        except Exception as e:
            logger.error(f"Error selling stock: {str(e)}")
            raise
    
    @staticmethod
    @transaction.atomic
    def transfer_stock(product, from_location, to_location, quantity,
                      reference_type=None, reference_id=None, reference_number=None,
                      notes=None):
        """
        Transfer stock between locations
        """
        try:
            # Get source stock
            from_stock = Stock.objects.get(product=product, location=from_location)
            
            # Check availability
            if from_stock.quantity_sellable < quantity:
                raise ValueError(f"Insufficient stock for transfer. Available: {from_stock.quantity_sellable}, Requested: {quantity}")
            
            # Get or create destination stock
            to_stock = StockService.get_or_create_stock(product, to_location)
            
            # Create outbound movement
            out_movement = StockMovement.objects.create(
                product=product,
                location=from_location,
                movement_type='TRANSFER_OUT',
                quantity=-quantity,
                quantity_sellable=-quantity,
                unit_cost=from_stock.average_cost,
                from_location=from_location,
                to_location=to_location,
                reference_type=reference_type,
                reference_id=reference_id,
                reference_number=reference_number,
                notes=notes,
                status='COMPLETED'
            )
            
            # Create inbound movement
            in_movement = StockMovement.objects.create(
                product=product,
                location=to_location,
                movement_type='TRANSFER_IN',
                quantity=quantity,
                quantity_sellable=quantity,
                unit_cost=from_stock.average_cost,
                from_location=from_location,
                to_location=to_location,
                reference_type=reference_type,
                reference_id=reference_id,
                reference_number=reference_number,
                notes=notes,
                status='COMPLETED'
            )
            
            # Update source stock
            from_stock.quantity_sellable -= quantity
            from_stock.quantity_on_hand -= quantity
            from_stock.save()
            
            # Update destination stock
            if to_stock.quantity_on_hand > 0:
                total_value = (to_stock.average_cost * to_stock.quantity_on_hand) + (from_stock.average_cost * quantity)
                to_stock.average_cost = total_value / (to_stock.quantity_on_hand + quantity)
            else:
                to_stock.average_cost = from_stock.average_cost
            
            to_stock.quantity_sellable += quantity
            to_stock.quantity_on_hand += quantity
            to_stock.last_received_date = timezone.now()
            to_stock.save()
            
            logger.info(f"Transferred {quantity} units of {product.name} from {from_location.name} to {to_location.name}")
            return out_movement, in_movement
            
        except Stock.DoesNotExist:
            raise ValueError(f"No stock found for {product.name} at {from_location.name}")
        except Exception as e:
            logger.error(f"Error transferring stock: {str(e)}")
            raise
    
    @staticmethod
    @transaction.atomic
    def adjust_stock(product, location, quantity_change, reason,
                    adjustment_type='ADJUSTMENT_IN', unit_cost=None,
                    reference_type=None, reference_id=None, reference_number=None,
                    notes=None):
        """
        Adjust stock quantities (positive or negative)
        """
        try:
            # Get or create stock record
            stock = StockService.get_or_create_stock(product, location)
            
            # Determine movement type
            if quantity_change > 0:
                movement_type = 'ADJUSTMENT_IN'
                sellable_change = quantity_change
            else:
                movement_type = 'ADJUSTMENT_OUT'
                sellable_change = quantity_change
                
                # Check if we have enough stock for negative adjustment
                if abs(quantity_change) > stock.quantity_sellable:
                    raise ValueError(f"Cannot adjust stock below zero. Current: {stock.quantity_sellable}, Adjustment: {quantity_change}")
            
            # Use current average cost if not provided
            if unit_cost is None:
                unit_cost = stock.average_cost
            
            # Create stock movement
            movement = StockMovement.objects.create(
                product=product,
                location=location,
                movement_type=movement_type,
                quantity=quantity_change,
                quantity_sellable=sellable_change,
                unit_cost=unit_cost,
                reference_type=reference_type,
                reference_id=reference_id,
                reference_number=reference_number,
                reason=reason,
                notes=notes,
                status='COMPLETED'
            )
            
            # Update stock quantities
            stock.quantity_sellable += sellable_change
            stock.quantity_on_hand += quantity_change
            
            # Update cost if positive adjustment
            if quantity_change > 0 and stock.quantity_on_hand > 0:
                total_value = (stock.average_cost * (stock.quantity_on_hand - quantity_change)) + (unit_cost * quantity_change)
                stock.average_cost = total_value / stock.quantity_on_hand
            
            stock.save()
            
            logger.info(f"Adjusted {product.name} at {location.name} by {quantity_change} units. Reason: {reason}")
            return movement
            
        except Exception as e:
            logger.error(f"Error adjusting stock: {str(e)}")
            raise
    
    @staticmethod
    @transaction.atomic
    def mark_stock_non_sellable(product, location, quantity, reason,
                               reference_type=None, reference_id=None, notes=None):
        """
        Mark stock as non-sellable (damaged, reserved, etc.)
        """
        try:
            stock = Stock.objects.get(product=product, location=location)
            
            # Check availability
            if stock.quantity_sellable < quantity:
                raise ValueError(f"Insufficient sellable stock. Available: {stock.quantity_sellable}, Requested: {quantity}")
            
            # Create stock movement
            movement = StockMovement.objects.create(
                product=product,
                location=location,
                movement_type='DAMAGE',
                quantity=Decimal('0.00'),  # No change in total quantity
                quantity_sellable=-quantity,
                quantity_non_sellable=quantity,
                unit_cost=stock.average_cost,
                reference_type=reference_type,
                reference_id=reference_id,
                reason=reason,
                notes=notes,
                status='COMPLETED'
            )
            
            # Update stock quantities
            stock.quantity_sellable -= quantity
            stock.quantity_non_sellable += quantity
            stock.save()
            
            logger.info(f"Marked {quantity} units of {product.name} at {location.name} as non-sellable. Reason: {reason}")
            return movement
            
        except Stock.DoesNotExist:
            raise ValueError(f"No stock found for {product.name} at {location.name}")
        except Exception as e:
            logger.error(f"Error marking stock non-sellable: {str(e)}")
            raise
    
    @staticmethod
    @transaction.atomic
    def reserve_stock(product, location, quantity, 
                     reference_type=None, reference_id=None, notes=None):
        """
        Reserve stock for assembly or other purposes
        """
        try:
            stock = Stock.objects.get(product=product, location=location)
            
            # Check availability
            if stock.quantity_sellable < quantity:
                raise ValueError(f"Insufficient sellable stock for reservation. Available: {stock.quantity_sellable}, Requested: {quantity}")
            
            # Update stock quantities
            stock.quantity_sellable -= quantity
            stock.quantity_reserved += quantity
            stock.save()
            
            logger.info(f"Reserved {quantity} units of {product.name} at {location.name}")
            return True
            
        except Stock.DoesNotExist:
            raise ValueError(f"No stock found for {product.name} at {location.name}")
        except Exception as e:
            logger.error(f"Error reserving stock: {str(e)}")
            raise
    
    @staticmethod
    @transaction.atomic
    def unreserve_stock(product, location, quantity):
        """
        Unreserve stock (make it sellable again)
        """
        try:
            stock = Stock.objects.get(product=product, location=location)
            
            # Check reserved quantity
            if stock.quantity_reserved < quantity:
                raise ValueError(f"Cannot unreserve more than reserved. Reserved: {stock.quantity_reserved}, Requested: {quantity}")
            
            # Update stock quantities
            stock.quantity_reserved -= quantity
            stock.quantity_sellable += quantity
            stock.save()
            
            logger.info(f"Unreserved {quantity} units of {product.name} at {location.name}")
            return True
            
        except Stock.DoesNotExist:
            raise ValueError(f"No stock found for {product.name} at {location.name}")
        except Exception as e:
            logger.error(f"Error unreserving stock: {str(e)}")
            raise
    
    @staticmethod
    def get_stock_summary(product=None, location=None):
        """
        Get stock summary with filtering options
        """
        queryset = Stock.objects.select_related('product', 'location')
        
        if product:
            queryset = queryset.filter(product=product)
        if location:
            queryset = queryset.filter(location=location)
        
        return queryset.filter(quantity_on_hand__gt=0)
    
    @staticmethod
    def get_low_stock_items(location=None):
        """
        Get items that are below minimum stock level or at reorder point
        """
        queryset = Stock.objects.select_related('product', 'location').filter(
            quantity_on_hand__lte=models.F('reorder_point')
        )
        
        if location:
            queryset = queryset.filter(location=location)
        
        return queryset
    
    @staticmethod
    def get_stock_movements(product=None, location=None, movement_type=None, 
                          start_date=None, end_date=None, limit=100):
        """
        Get stock movements with filtering options
        """
        queryset = StockMovement.objects.select_related('product', 'location')
        
        if product:
            queryset = queryset.filter(product=product)
        if location:
            queryset = queryset.filter(location=location)
        if movement_type:
            queryset = queryset.filter(movement_type=movement_type)
        if start_date:
            queryset = queryset.filter(movement_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(movement_date__lte=end_date)
        
        return queryset[:limit]




class AssemblyOrderService:
    """Service for managing assembly orders and manufacturing operations"""
    
    @staticmethod
    @transaction.atomic
    def create_assembly_order(product, bom, quantity_to_produce, production_location,
                            planned_start_date, planned_completion_date,
                            reference_type=None, reference_id=None, reference_number=None,
                            priority='NORMAL', description=None, notes=None):
        """
        Create a new assembly order
        """
        try:
            from .models import AssemblyOrder, AssemblyOrderItem
            
            # Generate order number
            order_count = AssemblyOrder.objects.count() + 1
            order_number = f"AO{order_count:06d}"
            
            # Calculate estimated costs
            material_requirements = []
            estimated_material_cost = Decimal('0.00')
            
            for bom_item in bom.bom_items.all():
                required_qty = bom_item.quantity_required * quantity_to_produce
                item_cost = bom_item.total_cost * quantity_to_produce
                estimated_material_cost += item_cost
                
                material_requirements.append({
                    'bom_item': bom_item,
                    'planned_quantity': required_qty * (1 + bom_item.waste_percentage / 100),
                    'unit_cost': bom_item.unit_cost,
                })
            
            # Create assembly order
            assembly_order = AssemblyOrder.objects.create(
                order_number=order_number,
                product=product,
                bom=bom,
                quantity_to_produce=quantity_to_produce,
                production_location=production_location,
                planned_start_date=planned_start_date,
                planned_completion_date=planned_completion_date,
                priority=priority,
                estimated_material_cost=estimated_material_cost,
                estimated_labor_cost=bom.labor_cost_per_unit * quantity_to_produce,
                estimated_overhead_cost=bom.overhead_cost_per_unit * quantity_to_produce,
                reference_type=reference_type,
                reference_id=reference_id,
                reference_number=reference_number,
                description=description,
                notes=notes,
                status='DRAFT'
            )
            
            # Create assembly order items
            for req in material_requirements:
                AssemblyOrderItem.objects.create(
                    assembly_order=assembly_order,
                    component=req['bom_item'].component,
                    bom_item=req['bom_item'],
                    planned_quantity=req['planned_quantity'],
                    unit_cost=req['unit_cost'],
                    sequence_number=req['bom_item'].sequence_number,
                    status='PLANNED'
                )
            
            logger.info(f"Created assembly order {order_number} for {quantity_to_produce} units of {product.name}")
            return assembly_order
            
        except Exception as e:
            logger.error(f"Error creating assembly order: {str(e)}")
            raise
    
    @staticmethod
    @transaction.atomic
    def release_assembly_order(assembly_order):
        """
        Release assembly order for production (allocate materials)
        """
        try:
            from .models import AssemblyOrderItem
            
            if assembly_order.status != 'DRAFT':
                raise ValueError(f"Assembly order {assembly_order.order_number} is not in DRAFT status")
            
            # Check material availability
            availability = assembly_order.check_material_availability()
            shortages = [item for item in availability if not item['is_available']]
            
            if shortages:
                critical_shortages = [item for item in shortages if item['is_critical']]
                if critical_shortages:
                    shortage_details = ', '.join([f"{item['component'].name}: {item['shortage']}" for item in critical_shortages])
                    raise ValueError(f"Critical material shortages: {shortage_details}")
            
            # Allocate materials (reserve stock)
            for order_item in assembly_order.order_items.all():
                try:
                    # Reserve stock for this component
                    StockService.reserve_stock(
                        product=order_item.component,
                        location=assembly_order.production_location,
                        quantity=order_item.planned_quantity,
                        reference_type='ASSEMBLY_ORDER',
                        reference_id=str(assembly_order.id),
                        notes=f"Reserved for Assembly Order {assembly_order.order_number}"
                    )
                    
                    # Update order item status
                    order_item.allocated_quantity = order_item.planned_quantity
                    order_item.status = 'ALLOCATED'
                    order_item.allocated_date = timezone.now()
                    order_item.save()
                    
                except Exception as e:
                    logger.warning(f"Could not allocate {order_item.component.name}: {str(e)}")
                    # Continue with partial allocation
            
            # Update assembly order status
            assembly_order.status = 'RELEASED'
            assembly_order.save()
            
            logger.info(f"Released assembly order {assembly_order.order_number}")
            return assembly_order
            
        except Exception as e:
            logger.error(f"Error releasing assembly order: {str(e)}")
            raise
    
    @staticmethod
    @transaction.atomic
    def start_production(assembly_order):
        """
        Start production on assembly order
        """
        try:
            if assembly_order.status != 'RELEASED':
                raise ValueError(f"Assembly order {assembly_order.order_number} is not released")
            
            assembly_order.status = 'IN_PROGRESS'
            assembly_order.actual_start_date = timezone.now()
            assembly_order.save()
            
            logger.info(f"Started production for assembly order {assembly_order.order_number}")
            return assembly_order
            
        except Exception as e:
            logger.error(f"Error starting production: {str(e)}")
            raise
    
    @staticmethod
    @transaction.atomic
    def consume_materials(assembly_order, material_consumptions):
        """
        Consume materials for production
        
        material_consumptions: list of dicts with keys:
        - component: Product instance
        - quantity: Decimal quantity consumed
        - lot_number: optional
        - notes: optional
        """
        try:
            from .models import AssemblyOrderItem
            
            if assembly_order.status not in ['IN_PROGRESS', 'RELEASED']:
                raise ValueError(f"Assembly order {assembly_order.order_number} is not in production")
            
            total_material_cost = Decimal('0.00')
            
            for consumption in material_consumptions:
                component = consumption['component']
                quantity = consumption['quantity']
                lot_number = consumption.get('lot_number')
                notes = consumption.get('notes')
                
                # Find the order item
                try:
                    order_item = assembly_order.order_items.get(component=component)
                except AssemblyOrderItem.DoesNotExist:
                    raise ValueError(f"Component {component.name} not found in assembly order")
                
                # Check if we have enough allocated quantity
                remaining_allocated = order_item.allocated_quantity - order_item.consumed_quantity
                if quantity > remaining_allocated:
                    raise ValueError(f"Cannot consume {quantity} of {component.name}. Only {remaining_allocated} allocated.")
                
                # Get stock record
                stock = Stock.objects.get(product=component, location=assembly_order.production_location)
                
                # Create stock movement for consumption
                movement = StockMovement.objects.create(
                    product=component,
                    location=assembly_order.production_location,
                    movement_type='ASSEMBLY_OUT',
                    quantity=-quantity,
                    quantity_sellable=Decimal('0.00'),  # Consumed from reserved
                    quantity_non_sellable=Decimal('0.00'),
                    unit_cost=stock.average_cost,
                    reference_type='ASSEMBLY_ORDER',
                    reference_id=str(assembly_order.id),
                    reference_number=assembly_order.order_number,
                    lot_number=lot_number,
                    notes=notes,
                    status='COMPLETED'
                )
                
                # Update stock quantities (reduce reserved, not sellable)
                stock.quantity_reserved -= quantity
                stock.quantity_on_hand -= quantity
                stock.save()
                
                # Update order item
                order_item.consumed_quantity += quantity
                order_item.unit_cost = stock.average_cost
                order_item.total_cost += quantity * stock.average_cost
                order_item.consumed_date = timezone.now()
                order_item.lot_number = lot_number
                if order_item.consumed_quantity >= order_item.planned_quantity:
                    order_item.status = 'CONSUMED'
                order_item.save()
                
                total_material_cost += quantity * stock.average_cost
            
            # Update assembly order actual material cost
            assembly_order.actual_material_cost += total_material_cost
            assembly_order.save()
            
            logger.info(f"Consumed materials for assembly order {assembly_order.order_number}")
            return True
            
        except Exception as e:
            logger.error(f"Error consuming materials: {str(e)}")
            raise
    
    @staticmethod
    @transaction.atomic
    def produce_finished_goods(assembly_order, quantity_produced, quantity_good=None,
                             quantity_scrapped=None, lot_number=None, batch_number=None,
                             expiry_date=None, labor_hours=None, labor_cost=None,
                             overhead_cost=None, operator=None, notes=None):
        """
        Record production of finished goods
        """
        try:
            from .models import AssemblyOrderProduction
            
            if assembly_order.status != 'IN_PROGRESS':
                raise ValueError(f"Assembly order {assembly_order.order_number} is not in progress")
            
            # Default values
            if quantity_good is None:
                quantity_good = quantity_produced
            if quantity_scrapped is None:
                quantity_scrapped = Decimal('0.00')
            
            # Validate quantities
            if quantity_good + quantity_scrapped != quantity_produced:
                raise ValueError("Good quantity + scrapped quantity must equal total produced quantity")
            
            # Create production record
            production = AssemblyOrderProduction.objects.create(
                assembly_order=assembly_order,
                quantity_produced=quantity_produced,
                quantity_good=quantity_good,
                quantity_scrapped=quantity_scrapped,
                lot_number=lot_number,
                batch_number=batch_number,
                expiry_date=expiry_date,
                labor_hours=labor_hours or Decimal('0.00'),
                labor_cost=labor_cost or Decimal('0.00'),
                overhead_cost=overhead_cost or Decimal('0.00'),
                operator=operator,
                notes=notes,
                status='COMPLETED'
            )
            
            # Add good quantity to inventory
            if quantity_good > 0:
                # Calculate unit cost
                unit_cost = assembly_order.bom.total_cost_per_unit
                
                # Create stock movement for finished goods
                movement = StockService.receive_stock(
                    product=assembly_order.product,
                    location=assembly_order.production_location,
                    quantity=quantity_good,
                    unit_cost=unit_cost,
                    reference_type='ASSEMBLY_ORDER',
                    reference_id=str(assembly_order.id),
                    reference_number=assembly_order.order_number,
                    lot_number=lot_number,
                    expiry_date=expiry_date,
                    notes=f"Produced from Assembly Order {assembly_order.order_number}"
                )
            
            # Update assembly order quantities
            assembly_order.quantity_produced += quantity_produced
            assembly_order.quantity_scrapped += quantity_scrapped
            assembly_order.actual_labor_cost += labor_cost or Decimal('0.00')
            assembly_order.actual_overhead_cost += overhead_cost or Decimal('0.00')
            
            # Check if order is complete
            if assembly_order.quantity_remaining <= 0:
                assembly_order.status = 'COMPLETED'
                assembly_order.actual_completion_date = timezone.now()
                
                # Unreserve any remaining allocated materials
                for order_item in assembly_order.order_items.filter(status='ALLOCATED'):
                    remaining_allocated = order_item.allocated_quantity - order_item.consumed_quantity
                    if remaining_allocated > 0:
                        StockService.unreserve_stock(
                            product=order_item.component,
                            location=assembly_order.production_location,
                            quantity=remaining_allocated
                        )
                        order_item.status = 'CONSUMED'
                        order_item.save()
            
            assembly_order.save()
            
            logger.info(f"Produced {quantity_produced} units for assembly order {assembly_order.order_number}")
            return production
            
        except Exception as e:
            logger.error(f"Error producing finished goods: {str(e)}")
            raise
    
    @staticmethod
    @transaction.atomic
    def cancel_assembly_order(assembly_order, reason=None):
        """
        Cancel assembly order and unreserve materials
        """
        try:
            if assembly_order.status in ['COMPLETED', 'CANCELLED']:
                raise ValueError(f"Assembly order {assembly_order.order_number} cannot be cancelled")
            
            # Unreserve allocated materials
            for order_item in assembly_order.order_items.filter(status='ALLOCATED'):
                remaining_allocated = order_item.allocated_quantity - order_item.consumed_quantity
                if remaining_allocated > 0:
                    StockService.unreserve_stock(
                        product=order_item.component,
                        location=assembly_order.production_location,
                        quantity=remaining_allocated
                    )
                order_item.status = 'CANCELLED'
                order_item.save()
            
            # Update assembly order
            assembly_order.status = 'CANCELLED'
            if reason:
                assembly_order.notes = f"{assembly_order.notes or ''}\nCancelled: {reason}".strip()
            assembly_order.save()
            
            logger.info(f"Cancelled assembly order {assembly_order.order_number}")
            return assembly_order
            
        except Exception as e:
            logger.error(f"Error cancelling assembly order: {str(e)}")
            raise
    
    @staticmethod
    def get_assembly_orders(status=None, product=None, location=None, 
                          start_date=None, end_date=None, limit=100):
        """
        Get assembly orders with filtering options
        """
        from .models import AssemblyOrder
        
        queryset = AssemblyOrder.objects.select_related('product', 'bom', 'production_location')
        
        if status:
            queryset = queryset.filter(status=status)
        if product:
            queryset = queryset.filter(product=product)
        if location:
            queryset = queryset.filter(production_location=location)
        if start_date:
            queryset = queryset.filter(planned_start_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(planned_completion_date__lte=end_date)
        
        return queryset[:limit]
    
    @staticmethod
    def get_material_requirements(assembly_orders=None, location=None):
        """
        Get consolidated material requirements for multiple assembly orders
        """
        from .models import AssemblyOrder
        from django.db.models import Sum
        
        if assembly_orders is None:
            queryset = AssemblyOrder.objects.filter(status__in=['RELEASED', 'IN_PROGRESS'])
            if location:
                queryset = queryset.filter(production_location=location)
            assembly_orders = queryset
        
        requirements = {}
        
        for order in assembly_orders:
            for order_item in order.order_items.filter(status__in=['PLANNED', 'ALLOCATED']):
                component = order_item.component
                remaining_qty = order_item.planned_quantity - order_item.consumed_quantity
                
                if component.id not in requirements:
                    requirements[component.id] = {
                        'component': component,
                        'total_required': Decimal('0.00'),
                        'orders': []
                    }
                
                requirements[component.id]['total_required'] += remaining_qty
                requirements[component.id]['orders'].append({
                    'order': order,
                    'quantity': remaining_qty,
                    'due_date': order.planned_completion_date
                })
        
        return list(requirements.values())

