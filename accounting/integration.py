"""
Accounting Integration Services
Automatically creates journal entries for sales, purchasing, and inventory transactions
"""

from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import Account, JournalEntry, JournalEntryLine
from sales.models import SalesOrder, Invoice, Payment as SalesPayment
from purchasing.models import PurchaseOrder, Bill, SupplierPayment
from inventory.models import StockMovement

User = get_user_model()

class AccountingIntegrationService:
    """Service class for creating automatic journal entries"""
    
    @staticmethod
    def get_default_accounts():
        """Get default accounts for automatic entries"""
        try:
            accounts = {
                'cash': Account.objects.filter(cash_account=True, is_active=True).first(),
                'bank': Account.objects.filter(bank_account=True, is_active=True).first(),
                'accounts_receivable': Account.objects.filter(code='1200', is_active=True).first(),
                'accounts_payable': Account.objects.filter(code='2100', is_active=True).first(),
                'sales_revenue': Account.objects.filter(code='4100', is_active=True).first(),
                'cost_of_goods_sold': Account.objects.filter(code='5100', is_active=True).first(),
                'inventory': Account.objects.filter(code='1300', is_active=True).first(),
                'purchase_expense': Account.objects.filter(code='5200', is_active=True).first(),
                'tax_payable': Account.objects.filter(code='2200', is_active=True).first(),
                'tax_receivable': Account.objects.filter(code='1400', is_active=True).first(),
            }
            return accounts
        except Exception as e:
            print(f"Error getting default accounts: {e}")
            return {}
    
    @classmethod
    def create_sales_order_entry(cls, sales_order, user=None):
        """Create journal entry for sales order"""
        if not user:
            user = User.objects.filter(is_staff=True).first()
        
        accounts = cls.get_default_accounts()
        if not accounts.get('accounts_receivable') or not accounts.get('sales_revenue'):
            return None
        
        try:
            with transaction.atomic():
                # Calculate totals
                subtotal = sales_order.subtotal
                tax_amount = sales_order.tax_amount
                total_amount = sales_order.total_amount
                
                journal_entry = JournalEntry.objects.create(
                    entry_date=sales_order.order_date,
                    entry_type='SALES',
                    reference_number=sales_order.order_number,
                    description=f'Sales Order #{sales_order.order_number} - {sales_order.customer.name}',
                    created_by=user,
                    status='DRAFT'
                )
                
                # Debit: Accounts Receivable
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=accounts['accounts_receivable'],
                    description=f'Sales to {sales_order.customer.name}',
                    debit_amount=total_amount,
                    credit_amount=Decimal('0.00')
                )
                
                # Credit: Sales Revenue
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=accounts['sales_revenue'],
                    description=f'Sales revenue - {sales_order.customer.name}',
                    debit_amount=Decimal('0.00'),
                    credit_amount=subtotal
                )
                
                # Credit: Tax Payable (if applicable)
                if tax_amount > 0 and accounts.get('tax_payable'):
                    JournalEntryLine.objects.create(
                        journal_entry=journal_entry,
                        account=accounts['tax_payable'],
                        description=f'Sales tax - {sales_order.customer.name}',
                        debit_amount=Decimal('0.00'),
                        credit_amount=tax_amount
                    )
                
                # Auto-post the entry
                journal_entry.post_entry(user)
                
                return journal_entry
                
        except Exception as e:
            print(f"Error creating sales order journal entry: {e}")
            return None
    
    @classmethod
    def create_sales_payment_entry(cls, payment, user=None):
        """Create journal entry for sales payment"""
        if not user:
            user = User.objects.filter(is_staff=True).first()
        
        accounts = cls.get_default_accounts()
        cash_or_bank = accounts.get('cash') if payment.payment_method == 'CASH' else accounts.get('bank')
        
        if not cash_or_bank or not accounts.get('accounts_receivable'):
            return None
        
        try:
            with transaction.atomic():
                journal_entry = JournalEntry.objects.create(
                    entry_date=payment.payment_date,
                    entry_type='RECEIPT',
                    reference_number=payment.reference_number,
                    description=f'Payment received from {payment.invoice.customer.name}',
                    created_by=user,
                    status='DRAFT'
                )
                
                # Debit: Cash/Bank
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=cash_or_bank,
                    description=f'Payment from {payment.invoice.customer.name}',
                    debit_amount=payment.amount,
                    credit_amount=Decimal('0.00')
                )
                
                # Credit: Accounts Receivable
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=accounts['accounts_receivable'],
                    description=f'Payment from {payment.invoice.customer.name}',
                    debit_amount=Decimal('0.00'),
                    credit_amount=payment.amount
                )
                
                # Auto-post the entry
                journal_entry.post_entry(user)
                
                return journal_entry
                
        except Exception as e:
            print(f"Error creating sales payment journal entry: {e}")
            return None
    
    @classmethod
    def create_purchase_order_entry(cls, purchase_order, user=None):
        """Create journal entry for purchase order"""
        if not user:
            user = User.objects.filter(is_staff=True).first()
        
        accounts = cls.get_default_accounts()
        if not accounts.get('accounts_payable') or not accounts.get('purchase_expense'):
            return None
        
        try:
            with transaction.atomic():
                # Calculate totals
                subtotal = purchase_order.subtotal
                tax_amount = purchase_order.tax_amount
                total_amount = purchase_order.total_amount
                
                journal_entry = JournalEntry.objects.create(
                    entry_date=purchase_order.order_date,
                    entry_type='PURCHASE',
                    reference_number=purchase_order.order_number,
                    description=f'Purchase Order #{purchase_order.order_number} - {purchase_order.supplier.name}',
                    created_by=user,
                    status='DRAFT'
                )
                
                # Debit: Purchase Expense or Inventory
                expense_account = accounts.get('inventory') or accounts['purchase_expense']
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=expense_account,
                    description=f'Purchase from {purchase_order.supplier.name}',
                    debit_amount=subtotal,
                    credit_amount=Decimal('0.00')
                )
                
                # Debit: Tax Receivable (if applicable)
                if tax_amount > 0 and accounts.get('tax_receivable'):
                    JournalEntryLine.objects.create(
                        journal_entry=journal_entry,
                        account=accounts['tax_receivable'],
                        description=f'Purchase tax - {purchase_order.supplier.name}',
                        debit_amount=tax_amount,
                        credit_amount=Decimal('0.00')
                    )
                
                # Credit: Accounts Payable
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=accounts['accounts_payable'],
                    description=f'Purchase from {purchase_order.supplier.name}',
                    debit_amount=Decimal('0.00'),
                    credit_amount=total_amount
                )
                
                # Auto-post the entry
                journal_entry.post_entry(user)
                
                return journal_entry
                
        except Exception as e:
            print(f"Error creating purchase order journal entry: {e}")
            return None
    
    @classmethod
    def create_supplier_payment_entry(cls, payment, user=None):
        """Create journal entry for supplier payment"""
        if not user:
            user = User.objects.filter(is_staff=True).first()
        
        accounts = cls.get_default_accounts()
        cash_or_bank = accounts.get('cash') if payment.payment_method == 'CASH' else accounts.get('bank')
        
        if not cash_or_bank or not accounts.get('accounts_payable'):
            return None
        
        try:
            with transaction.atomic():
                journal_entry = JournalEntry.objects.create(
                    entry_date=payment.payment_date,
                    entry_type='PAYMENT',
                    reference_number=payment.reference_number,
                    description=f'Payment to {payment.bill.supplier.name}',
                    created_by=user,
                    status='DRAFT'
                )
                
                # Debit: Accounts Payable
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=accounts['accounts_payable'],
                    description=f'Payment to {payment.bill.supplier.name}',
                    debit_amount=payment.amount,
                    credit_amount=Decimal('0.00')
                )
                
                # Credit: Cash/Bank
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=cash_or_bank,
                    description=f'Payment to {payment.bill.supplier.name}',
                    debit_amount=Decimal('0.00'),
                    credit_amount=payment.amount
                )
                
                # Auto-post the entry
                journal_entry.post_entry(user)
                
                return journal_entry
                
        except Exception as e:
            print(f"Error creating supplier payment journal entry: {e}")
            return None
    
    @classmethod
    def create_inventory_adjustment_entry(cls, stock_movement, user=None):
        """Create journal entry for inventory adjustments"""
        if not user:
            user = User.objects.filter(is_staff=True).first()
        
        accounts = cls.get_default_accounts()
        if not accounts.get('inventory') or not accounts.get('cost_of_goods_sold'):
            return None
        
        # Only create entries for certain movement types
        if stock_movement.movement_type not in ['ADJUSTMENT', 'SALE', 'PRODUCTION']:
            return None
        
        try:
            with transaction.atomic():
                journal_entry = JournalEntry.objects.create(
                    entry_date=stock_movement.movement_date,
                    entry_type='INVENTORY',
                    reference_number=stock_movement.reference_number,
                    description=f'Inventory {stock_movement.movement_type} - {stock_movement.product.name}',
                    created_by=user,
                    status='DRAFT'
                )
                
                # Calculate value
                movement_value = stock_movement.quantity * stock_movement.unit_cost
                
                if stock_movement.movement_type == 'ADJUSTMENT':
                    if stock_movement.quantity > 0:
                        # Positive adjustment - increase inventory
                        JournalEntryLine.objects.create(
                            journal_entry=journal_entry,
                            account=accounts['inventory'],
                            description=f'Inventory increase - {stock_movement.product.name}',
                            debit_amount=movement_value,
                            credit_amount=Decimal('0.00')
                        )
                        # Credit to adjustment account (could be expense or other)
                        JournalEntryLine.objects.create(
                            journal_entry=journal_entry,
                            account=accounts['cost_of_goods_sold'],
                            description=f'Inventory adjustment - {stock_movement.product.name}',
                            debit_amount=Decimal('0.00'),
                            credit_amount=movement_value
                        )
                    else:
                        # Negative adjustment - decrease inventory
                        JournalEntryLine.objects.create(
                            journal_entry=journal_entry,
                            account=accounts['cost_of_goods_sold'],
                            description=f'Inventory decrease - {stock_movement.product.name}',
                            debit_amount=abs(movement_value),
                            credit_amount=Decimal('0.00')
                        )
                        JournalEntryLine.objects.create(
                            journal_entry=journal_entry,
                            account=accounts['inventory'],
                            description=f'Inventory adjustment - {stock_movement.product.name}',
                            debit_amount=Decimal('0.00'),
                            credit_amount=abs(movement_value)
                        )
                
                elif stock_movement.movement_type == 'SALE':
                    # Sale - decrease inventory, increase COGS
                    JournalEntryLine.objects.create(
                        journal_entry=journal_entry,
                        account=accounts['cost_of_goods_sold'],
                        description=f'Cost of goods sold - {stock_movement.product.name}',
                        debit_amount=abs(movement_value),
                        credit_amount=Decimal('0.00')
                    )
                    JournalEntryLine.objects.create(
                        journal_entry=journal_entry,
                        account=accounts['inventory'],
                        description=f'Inventory sold - {stock_movement.product.name}',
                        debit_amount=Decimal('0.00'),
                        credit_amount=abs(movement_value)
                    )
                
                # Auto-post the entry
                journal_entry.post_entry(user)
                
                return journal_entry
                
        except Exception as e:
            print(f"Error creating inventory adjustment journal entry: {e}")
            return None


# Signal handlers for automatic journal entry creation
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=SalesOrder)
def create_sales_order_journal_entry(sender, instance, created, **kwargs):
    """Automatically create journal entry when sales order is created"""
    if created and instance.status == 'CONFIRMED':
        AccountingIntegrationService.create_sales_order_entry(instance)

@receiver(post_save, sender=SalesPayment)
def create_sales_payment_journal_entry(sender, instance, created, **kwargs):
    """Automatically create journal entry when sales payment is received"""
    if created:
        AccountingIntegrationService.create_sales_payment_entry(instance)

@receiver(post_save, sender=PurchaseOrder)
def create_purchase_order_journal_entry(sender, instance, created, **kwargs):
    """Automatically create journal entry when purchase order is created"""
    if created and instance.status == 'CONFIRMED':
        AccountingIntegrationService.create_purchase_order_entry(instance)

@receiver(post_save, sender=SupplierPayment)
def create_supplier_payment_journal_entry(sender, instance, created, **kwargs):
    """Automatically create journal entry when supplier payment is made"""
    if created:
        AccountingIntegrationService.create_supplier_payment_entry(instance)

@receiver(post_save, sender=StockMovement)
def create_inventory_journal_entry(sender, instance, created, **kwargs):
    """Automatically create journal entry for inventory movements"""
    if created:
        AccountingIntegrationService.create_inventory_adjustment_entry(instance)
