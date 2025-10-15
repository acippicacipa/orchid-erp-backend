import pandas as pd
import json
from datetime import datetime
from django.db import transaction
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from .models import ImportTemplate, DataImport, ImportError, ImportLog
from inventory.models import Product, MainCategory, SubCategory, Location, Stock
from sales.models import Customer, SalesOrder, SalesOrderItem, Invoice, Payment
from purchasing.models import Supplier, PurchaseOrder, PurchaseOrderItem, Bill, SupplierPayment
from accounting.models import Account, JournalEntry, JournalItem, Ledger
import logging

logger = logging.getLogger(__name__)

class DataImportService:
    """
    Core service for handling data imports across all modules
    """
    
    def __init__(self, data_import_id):
        self.data_import = DataImport.objects.get(id=data_import_id)
        self.template = self.data_import.template
        self.errors = []
        self.logs = []
    
    def validate_file(self):
        """
        Validate the uploaded file structure and data
        """
        try:
            self.data_import.status = 'VALIDATING'
            self.data_import.save()
            
            # Read the file
            if self.data_import.file.name.endswith('.csv'):
                df = pd.read_csv(self.data_import.file.path)
            elif self.data_import.file.name.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(self.data_import.file.path)
            else:
                raise ValidationError("Unsupported file format. Please use CSV or Excel files.")
            
            self.data_import.total_rows = len(df)
            
            # Validate required columns
            required_columns = self.template.required_columns
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                self._add_error(0, None, 'MISSING_COLUMN', 
                              f"Missing required columns: {', '.join(missing_columns)}")
                self.data_import.status = 'INVALID'
                self.data_import.save()
                return False
            
            # Validate data based on template type
            valid_rows = 0
            for index, row in df.iterrows():
                if self._validate_row(index + 1, row):
                    valid_rows += 1
            
            self.data_import.valid_rows = valid_rows
            self.data_import.invalid_rows = self.data_import.total_rows - valid_rows
            
            if self.data_import.valid_rows > 0:
                self.data_import.status = 'VALID'
            else:
                self.data_import.status = 'INVALID'
            
            self.data_import.save()
            self._save_errors_and_logs()
            
            return self.data_import.status == 'VALID'
            
        except Exception as e:
            self._add_log('ERROR', f"Validation failed: {str(e)}")
            self.data_import.status = 'INVALID'
            self.data_import.save()
            self._save_errors_and_logs()
            return False
    
    def import_data(self):
        """
        Import validated data into the database
        """
        if self.data_import.status != 'VALID':
            raise ValidationError("Cannot import invalid data")
        
        try:
            self.data_import.status = 'IMPORTING'
            self.data_import.started_at = datetime.now()
            self.data_import.save()
            
            # Read the file again
            if self.data_import.file.name.endswith('.csv'):
                df = pd.read_csv(self.data_import.file.path)
            else:
                df = pd.read_excel(self.data_import.file.path)
            
            imported_count = 0
            
            with transaction.atomic():
                for index, row in df.iterrows():
                    if self._import_row(index + 1, row):
                        imported_count += 1
            
            self.data_import.imported_rows = imported_count
            self.data_import.status = 'COMPLETED'
            self.data_import.completed_at = datetime.now()
            self.data_import.save()
            
            self._add_log('INFO', f"Successfully imported {imported_count} rows")
            self._save_errors_and_logs()
            
            return True
            
        except Exception as e:
            self._add_log('ERROR', f"Import failed: {str(e)}")
            self.data_import.status = 'FAILED'
            self.data_import.save()
            self._save_errors_and_logs()
            return False
    
    def _validate_row(self, row_number, row):
        """
        Validate a single row based on template type
        """
        template_type = self.template.template_type
        
        try:
            if template_type == 'CUSTOMERS':
                return self._validate_customer_row(row_number, row)
            elif template_type == 'SUPPLIERS':
                return self._validate_supplier_row(row_number, row)
            elif template_type == 'ITEMS':
                return self._validate_product_row(row_number, row)
            elif template_type == 'INVENTORY':
                return self._validate_inventory_row(row_number, row)
            elif template_type == 'CATEGORIES':
                return self._validate_category_row(row_number, row)
            elif template_type == 'LOCATIONS':
                return self._validate_location_row(row_number, row)
            elif template_type == 'SALES_ORDERS':
                return self._validate_sales_order_row(row_number, row)
            elif template_type == 'INVOICES':
                return self._validate_invoice_row(row_number, row)
            elif template_type == 'PAYMENTS':
                return self._validate_payment_row(row_number, row)
            elif template_type == 'PURCHASE_ORDERS':
                return self._validate_purchase_order_row(row_number, row)
            elif template_type == 'BILLS':
                return self._validate_bill_row(row_number, row)
            elif template_type == 'SUPPLIER_PAYMENTS':
                return self._validate_supplier_payment_row(row_number, row)
            elif template_type == 'ACCOUNTS':
                return self._validate_account_row(row_number, row)
            elif template_type == 'JOURNAL_ENTRIES':
                return self._validate_journal_entry_row(row_number, row)
            else:
                self._add_error(row_number, None, 'VALIDATION_ERROR', 
                              f"Unknown template type: {template_type}")
                return False
        except Exception as e:
            self._add_error(row_number, None, 'VALIDATION_ERROR', str(e))
            return False
    
    def _import_row(self, row_number, row):
        """
        Import a single validated row
        """
        template_type = self.template.template_type
        
        try:
            if template_type == 'CUSTOMERS':
                return self._import_customer_row(row_number, row)
            elif template_type == 'SUPPLIERS':
                return self._import_supplier_row(row_number, row)
            elif template_type == 'ITEMS':
                return self._import_product_row(row_number, row)
            elif template_type == 'INVENTORY':
                return self._import_inventory_row(row_number, row)
            elif template_type == 'CATEGORIES':
                return self._import_category_row(row_number, row)
            elif template_type == 'LOCATIONS':
                return self._import_location_row(row_number, row)
            elif template_type == 'SALES_ORDERS':
                return self._import_sales_order_row(row_number, row)
            elif template_type == 'INVOICES':
                return self._import_invoice_row(row_number, row)
            elif template_type == 'PAYMENTS':
                return self._import_payment_row(row_number, row)
            elif template_type == 'PURCHASE_ORDERS':
                return self._import_purchase_order_row(row_number, row)
            elif template_type == 'BILLS':
                return self._import_bill_row(row_number, row)
            elif template_type == 'SUPPLIER_PAYMENTS':
                return self._import_supplier_payment_row(row_number, row)
            elif template_type == 'ACCOUNTS':
                return self._import_account_row(row_number, row)
            elif template_type == 'JOURNAL_ENTRIES':
                return self._import_journal_entry_row(row_number, row)
            else:
                return False
        except Exception as e:
            self._add_error(row_number, None, 'VALIDATION_ERROR', str(e))
            return False
    
    # Customer validation and import methods
    def _validate_customer_row(self, row_number, row):
        """Validate customer data"""
        is_valid = True
        
        # Check required fields
        if pd.isna(row.get('name')) or not str(row.get('name')).strip():
            self._add_error(row_number, 'name', 'VALIDATION_ERROR', 'Customer name is required')
            is_valid = False
        
        if pd.isna(row.get('email')) or not str(row.get('email')).strip():
            self._add_error(row_number, 'email', 'VALIDATION_ERROR', 'Customer email is required')
            is_valid = False
        else:
            # Check for duplicate email
            email = str(row.get('email')).strip()
            if Customer.objects.filter(email=email).exists():
                self._add_error(row_number, 'email', 'DUPLICATE_VALUE', f'Customer with email {email} already exists')
                is_valid = False
        
        return is_valid
    
    def _import_customer_row(self, row_number, row):
        """Import customer data"""
        customer = Customer.objects.create(
            name=str(row.get('name')).strip(),
            email=str(row.get('email')).strip(),
            phone=str(row.get('phone', '')).strip() or None,
            address=str(row.get('address', '')).strip() or None,
            city=str(row.get('city', '')).strip() or None,
            state=str(row.get('state', '')).strip() or None,
            postal_code=str(row.get('postal_code', '')).strip() or None,
            country=str(row.get('country', '')).strip() or None,
        )
        return True
    
    # Supplier validation and import methods
    def _validate_supplier_row(self, row_number, row):
        """Validate supplier data"""
        is_valid = True
        
        if pd.isna(row.get('name')) or not str(row.get('name')).strip():
            self._add_error(row_number, 'name', 'VALIDATION_ERROR', 'Supplier name is required')
            is_valid = False
        
        if pd.isna(row.get('email')) or not str(row.get('email')).strip():
            self._add_error(row_number, 'email', 'VALIDATION_ERROR', 'Supplier email is required')
            is_valid = False
        else:
            email = str(row.get('email')).strip()
            if Supplier.objects.filter(email=email).exists():
                self._add_error(row_number, 'email', 'DUPLICATE_VALUE', f'Supplier with email {email} already exists')
                is_valid = False
        
        return is_valid
    
    def _import_supplier_row(self, row_number, row):
        """Import supplier data"""
        supplier = Supplier.objects.create(
            name=str(row.get('name')).strip(),
            email=str(row.get('email')).strip(),
            phone=str(row.get('phone', '')).strip() or None,
            address=str(row.get('address', '')).strip() or None,
            city=str(row.get('city', '')).strip() or None,
            state=str(row.get('state', '')).strip() or None,
            postal_code=str(row.get('postal_code', '')).strip() or None,
            country=str(row.get('country', '')).strip() or None,
        )
        return True
    
    # Product validation and import methods
    def _validate_product_row(self, row_number, row):
        """Validate product data"""
        is_valid = True
        
        if pd.isna(row.get('name')) or not str(row.get('name')).strip():
            self._add_error(row_number, 'name', 'VALIDATION_ERROR', 'Product name is required')
            is_valid = False
        
        if pd.isna(row.get('sku')) or not str(row.get('sku')).strip():
            self._add_error(row_number, 'sku', 'VALIDATION_ERROR', 'Product SKU is required')
            is_valid = False
        else:
            sku = str(row.get('sku')).strip()
            if Product.objects.filter(sku=sku).exists():
                self._add_error(row_number, 'sku', 'DUPLICATE_VALUE', f'Product with SKU {sku} already exists')
                is_valid = False
        
        # Validate selling_price
        try:
            selling_price = float(row.get('selling_price', 0))
            if selling_price < 0:
                self._add_error(row_number, 'selling_price', 'VALIDATION_ERROR', 'Selling price cannot be negative')
                is_valid = False
        except (ValueError, TypeError):
            self._add_error(row_number, 'selling_price', 'DATA_TYPE_ERROR', 'Invalid selling_price format')
            is_valid = False
        
        # Validate main_category if provided
        main_category_name = row.get('main_category')
        if main_category_name and not pd.isna(main_category_name):
            if not MainCategory.objects.filter(name=str(main_category_name).strip()).exists():
                self._add_error(row_number, 'main_category', 'FOREIGN_KEY_ERROR', f'MainCategory "{main_category_name}" does not exist')
                is_valid = False

        # Validate sub_category if provided
        sub_category_name = row.get('sub_category')
        if sub_category_name and not pd.isna(sub_category_name):
            if not SubCategory.objects.filter(name=str(sub_category_name).strip()).exists():
                self._add_error(row_number, 'sub_category', 'FOREIGN_KEY_ERROR', f'SubCategory "{sub_category_name}" does not exist')
                is_valid = False
        
        return is_valid
    
    # ==============================================================================
    # PERUBAHAN #3: Sesuaikan impor produk
    # ==============================================================================
    def _import_product_row(self, row_number, row):
        """Import product data"""
        main_category = None
        main_category_name = row.get('main_category')
        if main_category_name and not pd.isna(main_category_name):
            main_category = MainCategory.objects.get(name=str(main_category_name).strip())

        sub_category = None
        sub_category_name = row.get('sub_category')
        if sub_category_name and not pd.isna(sub_category_name):
            sub_category = SubCategory.objects.get(name=str(sub_category_name).strip())
        
        product = Product.objects.create(
            name=str(row.get('name')).strip(),
            sku=str(row.get('sku')).strip(),
            description=str(row.get('description', '')).strip() or None,
            selling_price=float(row.get('selling_price', 0)),
            cost_price=float(row.get('cost_price', 0)) if row.get('cost_price') and not pd.isna(row.get('cost_price')) else 0.00,
            main_category=main_category,
            sub_category=sub_category,
            unit_of_measure=str(row.get('unit_of_measure', 'pcs')).strip(),
            is_active=True
        )
        return True
    
    # Category validation and import methods
    def _validate_category_row(self, row_number, row):
        """Validate category data"""
        is_valid = True
        
        if pd.isna(row.get('name')) or not str(row.get('name')).strip():
            self._add_error(row_number, 'name', 'VALIDATION_ERROR', 'Category name is required')
            is_valid = False
        else:
            name = str(row.get('name')).strip()
            if Category.objects.filter(name=name).exists():
                self._add_error(row_number, 'name', 'DUPLICATE_VALUE', f'Category with name {name} already exists')
                is_valid = False
        
        return is_valid
    
    def _import_category_row(self, row_number, row):
        """Import category data"""
        category = Category.objects.create(
            name=str(row.get('name')).strip(),
            description=str(row.get('description', '')).strip() or None,
        )
        return True
    
    # Location validation and import methods
    def _validate_location_row(self, row_number, row):
        """Validate location data"""
        is_valid = True
        
        if pd.isna(row.get('name')) or not str(row.get('name')).strip():
            self._add_error(row_number, 'name', 'VALIDATION_ERROR', 'Location name is required')
            is_valid = False
        else:
            name = str(row.get('name')).strip()
            if Location.objects.filter(name=name).exists():
                self._add_error(row_number, 'name', 'DUPLICATE_VALUE', f'Location with name {name} already exists')
                is_valid = False
        
        return is_valid
    
    def _import_location_row(self, row_number, row):
        """Import location data"""
        location = Location.objects.create(
            name=str(row.get('name')).strip(),
            address=str(row.get('address', '')).strip() or None,
            city=str(row.get('city', '')).strip() or None,
            state=str(row.get('state', '')).strip() or None,
            postal_code=str(row.get('postal_code', '')).strip() or None,
            country=str(row.get('country', '')).strip() or None,
        )
        return True
    
    # Inventory validation and import methods
    def _validate_inventory_row(self, row_number, row):
        """Validate inventory data"""
        is_valid = True
        
        # Validate product exists
        product_sku = row.get('product_sku')
        if pd.isna(product_sku) or not str(product_sku).strip():
            self._add_error(row_number, 'product_sku', 'VALIDATION_ERROR', 'Product SKU is required')
            is_valid = False
        else:
            if not Product.objects.filter(sku=str(product_sku).strip()).exists():
                self._add_error(row_number, 'product_sku', 'FOREIGN_KEY_ERROR', f'Product with SKU "{product_sku}" does not exist')
                is_valid = False
        
        # Validate warehouse exists
        warehouse_name = row.get('warehouse')
        if pd.isna(warehouse_name) or not str(warehouse_name).strip():
            self._add_error(row_number, 'warehouse', 'VALIDATION_ERROR', 'Warehouse is required')
            is_valid = False
        else:
            if not Warehouse.objects.filter(name=str(warehouse_name).strip()).exists():
                self._add_error(row_number, 'warehouse', 'FOREIGN_KEY_ERROR', f'Warehouse "{warehouse_name}" does not exist')
                is_valid = False
        
        # Validate quantity
        try:
            quantity = float(row.get('quantity', 0))
            if quantity < 0:
                self._add_error(row_number, 'quantity', 'VALIDATION_ERROR', 'Quantity cannot be negative')
                is_valid = False
        except (ValueError, TypeError):
            self._add_error(row_number, 'quantity', 'DATA_TYPE_ERROR', 'Invalid quantity format')
            is_valid = False
        
        return is_valid
    
    def _import_inventory_row(self, row_number, row):
        """Import inventory data"""
        product = Product.objects.get(sku=str(row.get('product_sku')).strip())
        warehouse = Warehouse.objects.get(name=str(row.get('warehouse')).strip())
        
        stock_level, created = StockLevel.objects.get_or_create(
            product=product,
            warehouse=warehouse,
            defaults={'quantity': float(row.get('quantity', 0))}
        )
        
        if not created:
            stock_level.quantity = float(row.get('quantity', 0))
            stock_level.save()
        
        return True
    
    # Sales Order validation and import methods
    def _validate_sales_order_row(self, row_number, row):
        """Validate sales order data"""
        is_valid = True
        
        # Validate customer exists
        customer_id = row.get('customer_id')
        if pd.isna(customer_id) or not str(customer_id).strip():
            self._add_error(row_number, 'customer_id', 'VALIDATION_ERROR', 'Customer ID is required')
            is_valid = False
        else:
            if not Customer.objects.filter(id=str(customer_id).strip()).exists():
                self._add_error(row_number, 'customer_id', 'FOREIGN_KEY_ERROR', f'Customer with ID "{customer_id}" does not exist')
                is_valid = False
        
        # Validate order date
        order_date = row.get('order_date')
        if pd.isna(order_date):
            self._add_error(row_number, 'order_date', 'VALIDATION_ERROR', 'Order date is required')
            is_valid = False
        
        # Validate total amount
        try:
            total_amount = float(row.get('total_amount', 0))
            if total_amount < 0:
                self._add_error(row_number, 'total_amount', 'VALIDATION_ERROR', 'Total amount cannot be negative')
                is_valid = False
        except (ValueError, TypeError):
            self._add_error(row_number, 'total_amount', 'DATA_TYPE_ERROR', 'Invalid total amount format')
            is_valid = False
        
        return is_valid
    
    def _import_sales_order_row(self, row_number, row):
        """Import sales order data"""
        customer = Customer.objects.get(id=str(row.get('customer_id')).strip())
        
        sales_order = SalesOrder.objects.create(
            customer=customer,
            order_date=row.get('order_date'),
            due_date=row.get('due_date'),
            order_number=str(row.get('order_number', '')).strip() or None,
            status=str(row.get('status', 'DRAFT')).strip(),
            total_amount=float(row.get('total_amount', 0)),
            discount_amount=float(row.get('discount_amount', 0)) if row.get('discount_amount') and not pd.isna(row.get('discount_amount')) else 0,
            tax_amount=float(row.get('tax_amount', 0)) if row.get('tax_amount') and not pd.isna(row.get('tax_amount')) else 0,
            notes=str(row.get('notes', '')).strip() or None,
            shipping_address_line_1=str(row.get('shipping_address_line_1', '')).strip() or None,
            shipping_city=str(row.get('shipping_city', '')).strip() or None,
            shipping_state=str(row.get('shipping_state', '')).strip() or None,
            shipping_postal_code=str(row.get('shipping_postal_code', '')).strip() or None,
            billing_address_line_1=str(row.get('billing_address_line_1', '')).strip() or None,
            billing_city=str(row.get('billing_city', '')).strip() or None,
            billing_state=str(row.get('billing_state', '')).strip() or None,
            billing_postal_code=str(row.get('billing_postal_code', '')).strip() or None,
        )
        return True
    
    # Invoice validation and import methods
    def _validate_invoice_row(self, row_number, row):
        """Validate invoice data"""
        is_valid = True
        
        # Validate customer exists
        customer_id = row.get('customer_id')
        if pd.isna(customer_id) or not str(customer_id).strip():
            self._add_error(row_number, 'customer_id', 'VALIDATION_ERROR', 'Customer ID is required')
            is_valid = False
        else:
            if not Customer.objects.filter(id=str(customer_id).strip()).exists():
                self._add_error(row_number, 'customer_id', 'FOREIGN_KEY_ERROR', f'Customer with ID "{customer_id}" does not exist')
                is_valid = False
        
        # Validate invoice date
        invoice_date = row.get('invoice_date')
        if pd.isna(invoice_date):
            self._add_error(row_number, 'invoice_date', 'VALIDATION_ERROR', 'Invoice date is required')
            is_valid = False
        
        # Validate total amount
        try:
            total_amount = float(row.get('total_amount', 0))
            if total_amount < 0:
                self._add_error(row_number, 'total_amount', 'VALIDATION_ERROR', 'Total amount cannot be negative')
                is_valid = False
        except (ValueError, TypeError):
            self._add_error(row_number, 'total_amount', 'DATA_TYPE_ERROR', 'Invalid total amount format')
            is_valid = False
        
        return is_valid
    
    def _import_invoice_row(self, row_number, row):
        """Import invoice data"""
        customer = Customer.objects.get(id=str(row.get('customer_id')).strip())
        
        # Try to find sales order if provided
        sales_order = None
        sales_order_number = row.get('sales_order_number')
        if sales_order_number and not pd.isna(sales_order_number):
            try:
                sales_order = SalesOrder.objects.get(order_number=str(sales_order_number).strip())
            except SalesOrder.DoesNotExist:
                pass
        
        invoice = Invoice.objects.create(
            customer=customer,
            sales_order=sales_order,
            invoice_date=row.get('invoice_date'),
            due_date=row.get('due_date'),
            invoice_number=str(row.get('invoice_number', '')).strip() or None,
            status=str(row.get('status', 'DRAFT')).strip(),
            total_amount=float(row.get('total_amount', 0)),
            amount_paid=float(row.get('amount_paid', 0)) if row.get('amount_paid') and not pd.isna(row.get('amount_paid')) else 0,
            balance_due=float(row.get('balance_due', 0)) if row.get('balance_due') and not pd.isna(row.get('balance_due')) else float(row.get('total_amount', 0)),
            notes=str(row.get('notes', '')).strip() or None,
        )
        return True
    
    # Payment validation and import methods
    def _validate_payment_row(self, row_number, row):
        """Validate payment data"""
        is_valid = True
        
        # Validate invoice exists
        invoice_number = row.get('invoice_number')
        if pd.isna(invoice_number) or not str(invoice_number).strip():
            self._add_error(row_number, 'invoice_number', 'VALIDATION_ERROR', 'Invoice number is required')
            is_valid = False
        else:
            if not Invoice.objects.filter(invoice_number=str(invoice_number).strip()).exists():
                self._add_error(row_number, 'invoice_number', 'FOREIGN_KEY_ERROR', f'Invoice with number "{invoice_number}" does not exist')
                is_valid = False
        
        # Validate payment date
        payment_date = row.get('payment_date')
        if pd.isna(payment_date):
            self._add_error(row_number, 'payment_date', 'VALIDATION_ERROR', 'Payment date is required')
            is_valid = False
        
        # Validate amount
        try:
            amount = float(row.get('amount', 0))
            if amount <= 0:
                self._add_error(row_number, 'amount', 'VALIDATION_ERROR', 'Payment amount must be positive')
                is_valid = False
        except (ValueError, TypeError):
            self._add_error(row_number, 'amount', 'DATA_TYPE_ERROR', 'Invalid amount format')
            is_valid = False
        
        return is_valid
    
    def _import_payment_row(self, row_number, row):
        """Import payment data"""
        invoice = Invoice.objects.get(invoice_number=str(row.get('invoice_number')).strip())
        
        payment = Payment.objects.create(
            invoice=invoice,
            payment_date=row.get('payment_date'),
            amount=float(row.get('amount', 0)),
            payment_method=str(row.get('payment_method', 'CASH')).strip(),
            transaction_id=str(row.get('transaction_id', '')).strip() or None,
            notes=str(row.get('notes', '')).strip() or None,
        )
        return True
    
    # Purchase Order validation and import methods
    def _validate_purchase_order_row(self, row_number, row):
        """Validate purchase order data"""
        is_valid = True
        
        # Validate supplier exists
        supplier_id = row.get('supplier_id')
        if pd.isna(supplier_id) or not str(supplier_id).strip():
            self._add_error(row_number, 'supplier_id', 'VALIDATION_ERROR', 'Supplier ID is required')
            is_valid = False
        else:
            if not Supplier.objects.filter(id=str(supplier_id).strip()).exists():
                self._add_error(row_number, 'supplier_id', 'FOREIGN_KEY_ERROR', f'Supplier with ID "{supplier_id}" does not exist')
                is_valid = False
        
        # Validate order date
        order_date = row.get('order_date')
        if pd.isna(order_date):
            self._add_error(row_number, 'order_date', 'VALIDATION_ERROR', 'Order date is required')
            is_valid = False
        
        # Validate total amount
        try:
            total_amount = float(row.get('total_amount', 0))
            if total_amount < 0:
                self._add_error(row_number, 'total_amount', 'VALIDATION_ERROR', 'Total amount cannot be negative')
                is_valid = False
        except (ValueError, TypeError):
            self._add_error(row_number, 'total_amount', 'DATA_TYPE_ERROR', 'Invalid total amount format')
            is_valid = False
        
        return is_valid
    
    def _import_purchase_order_row(self, row_number, row):
        """Import purchase order data"""
        supplier = Supplier.objects.get(id=str(row.get('supplier_id')).strip())
        
        purchase_order = PurchaseOrder.objects.create(
            supplier=supplier,
            order_date=row.get('order_date'),
            expected_delivery_date=row.get('expected_delivery_date'),
            order_number=str(row.get('order_number', '')).strip() or None,
            status=str(row.get('status', 'DRAFT')).strip(),
            total_amount=float(row.get('total_amount', 0)),
            notes=str(row.get('notes', '')).strip() or None,
        )
        return True
    
    # Bill validation and import methods
    def _validate_bill_row(self, row_number, row):
        """Validate bill data"""
        is_valid = True
        
        # Validate supplier exists
        supplier_id = row.get('supplier_id')
        if pd.isna(supplier_id) or not str(supplier_id).strip():
            self._add_error(row_number, 'supplier_id', 'VALIDATION_ERROR', 'Supplier ID is required')
            is_valid = False
        else:
            if not Supplier.objects.filter(id=str(supplier_id).strip()).exists():
                self._add_error(row_number, 'supplier_id', 'FOREIGN_KEY_ERROR', f'Supplier with ID "{supplier_id}" does not exist')
                is_valid = False
        
        # Validate bill date
        bill_date = row.get('bill_date')
        if pd.isna(bill_date):
            self._add_error(row_number, 'bill_date', 'VALIDATION_ERROR', 'Bill date is required')
            is_valid = False
        
        # Validate total amount
        try:
            total_amount = float(row.get('total_amount', 0))
            if total_amount < 0:
                self._add_error(row_number, 'total_amount', 'VALIDATION_ERROR', 'Total amount cannot be negative')
                is_valid = False
        except (ValueError, TypeError):
            self._add_error(row_number, 'total_amount', 'DATA_TYPE_ERROR', 'Invalid total amount format')
            is_valid = False
        
        return is_valid
    
    def _import_bill_row(self, row_number, row):
        """Import bill data"""
        supplier = Supplier.objects.get(id=str(row.get('supplier_id')).strip())
        
        # Try to find purchase order if provided
        purchase_order = None
        purchase_order_number = row.get('purchase_order_number')
        if purchase_order_number and not pd.isna(purchase_order_number):
            try:
                purchase_order = PurchaseOrder.objects.get(order_number=str(purchase_order_number).strip())
            except PurchaseOrder.DoesNotExist:
                pass
        
        bill = Bill.objects.create(
            supplier=supplier,
            purchase_order=purchase_order,
            bill_date=row.get('bill_date'),
            due_date=row.get('due_date'),
            bill_number=str(row.get('bill_number', '')).strip() or None,
            status=str(row.get('status', 'PENDING')).strip(),
            total_amount=float(row.get('total_amount', 0)),
            amount_paid=float(row.get('amount_paid', 0)) if row.get('amount_paid') and not pd.isna(row.get('amount_paid')) else 0,
            balance_due=float(row.get('balance_due', 0)) if row.get('balance_due') and not pd.isna(row.get('balance_due')) else float(row.get('total_amount', 0)),
            notes=str(row.get('notes', '')).strip() or None,
        )
        return True
    
    # Supplier Payment validation and import methods
    def _validate_supplier_payment_row(self, row_number, row):
        """Validate supplier payment data"""
        is_valid = True
        
        # Validate bill exists
        bill_number = row.get('bill_number')
        if pd.isna(bill_number) or not str(bill_number).strip():
            self._add_error(row_number, 'bill_number', 'VALIDATION_ERROR', 'Bill number is required')
            is_valid = False
        else:
            if not Bill.objects.filter(bill_number=str(bill_number).strip()).exists():
                self._add_error(row_number, 'bill_number', 'FOREIGN_KEY_ERROR', f'Bill with number "{bill_number}" does not exist')
                is_valid = False
        
        # Validate payment date
        payment_date = row.get('payment_date')
        if pd.isna(payment_date):
            self._add_error(row_number, 'payment_date', 'VALIDATION_ERROR', 'Payment date is required')
            is_valid = False
        
        # Validate amount
        try:
            amount = float(row.get('amount', 0))
            if amount <= 0:
                self._add_error(row_number, 'amount', 'VALIDATION_ERROR', 'Payment amount must be positive')
                is_valid = False
        except (ValueError, TypeError):
            self._add_error(row_number, 'amount', 'DATA_TYPE_ERROR', 'Invalid amount format')
            is_valid = False
        
        return is_valid
    
    def _import_supplier_payment_row(self, row_number, row):
        """Import supplier payment data"""
        bill = Bill.objects.get(bill_number=str(row.get('bill_number')).strip())
        
        supplier_payment = SupplierPayment.objects.create(
            bill=bill,
            payment_date=row.get('payment_date'),
            amount=float(row.get('amount', 0)),
            payment_method=str(row.get('payment_method', 'BANK_TRANSFER')).strip(),
            transaction_id=str(row.get('transaction_id', '')).strip() or None,
            notes=str(row.get('notes', '')).strip() or None,
        )
        return True
    
    # Account validation and import methods
    def _validate_account_row(self, row_number, row):
        """Validate account data"""
        is_valid = True
        
        # Validate account name
        if pd.isna(row.get('name')) or not str(row.get('name')).strip():
            self._add_error(row_number, 'name', 'VALIDATION_ERROR', 'Account name is required')
            is_valid = False
        
        # Validate account number
        account_number = row.get('account_number')
        if pd.isna(account_number) or not str(account_number).strip():
            self._add_error(row_number, 'account_number', 'VALIDATION_ERROR', 'Account number is required')
            is_valid = False
        else:
            if Account.objects.filter(account_number=str(account_number).strip()).exists():
                self._add_error(row_number, 'account_number', 'DUPLICATE_VALUE', f'Account with number {account_number} already exists')
                is_valid = False
        
        # Validate account type
        account_type = row.get('account_type')
        if pd.isna(account_type) or not str(account_type).strip():
            self._add_error(row_number, 'account_type', 'VALIDATION_ERROR', 'Account type is required')
            is_valid = False
        else:
            valid_types = ['ASSET', 'LIABILITY', 'EQUITY', 'REVENUE', 'EXPENSE']
            if str(account_type).strip().upper() not in valid_types:
                self._add_error(row_number, 'account_type', 'VALIDATION_ERROR', f'Account type must be one of: {", ".join(valid_types)}')
                is_valid = False
        
        return is_valid
    
    def _import_account_row(self, row_number, row):
        """Import account data"""
        account = Account.objects.create(
            name=str(row.get('name')).strip(),
            account_number=str(row.get('account_number')).strip(),
            account_type=str(row.get('account_type')).strip().upper(),
            description=str(row.get('description', '')).strip() or None,
            is_active=bool(row.get('is_active', True)),
        )
        return True
    
    # Journal Entry validation and import methods
    def _validate_journal_entry_row(self, row_number, row):
        """Validate journal entry data"""
        is_valid = True
        
        # Validate entry date
        entry_date = row.get('entry_date')
        if pd.isna(entry_date):
            self._add_error(row_number, 'entry_date', 'VALIDATION_ERROR', 'Entry date is required')
            is_valid = False
        
        # Validate reference number
        reference_number = row.get('reference_number')
        if pd.isna(reference_number) or not str(reference_number).strip():
            self._add_error(row_number, 'reference_number', 'VALIDATION_ERROR', 'Reference number is required')
            is_valid = False
        else:
            if JournalEntry.objects.filter(reference_number=str(reference_number).strip()).exists():
                self._add_error(row_number, 'reference_number', 'DUPLICATE_VALUE', f'Journal entry with reference number {reference_number} already exists')
                is_valid = False
        
        # Validate total debit and credit
        try:
            total_debit = float(row.get('total_debit', 0))
            total_credit = float(row.get('total_credit', 0))
            if total_debit != total_credit:
                self._add_error(row_number, 'total_debit', 'VALIDATION_ERROR', 'Total debit must equal total credit')
                is_valid = False
        except (ValueError, TypeError):
            self._add_error(row_number, 'total_debit', 'DATA_TYPE_ERROR', 'Invalid debit/credit amount format')
            is_valid = False
        
        return is_valid
    
    def _import_journal_entry_row(self, row_number, row):
        """Import journal entry data"""
        journal_entry = JournalEntry.objects.create(
            entry_date=row.get('entry_date'),
            reference_number=str(row.get('reference_number')).strip(),
            entry_type=str(row.get('entry_type', 'GENERAL')).strip(),
            description=str(row.get('description', '')).strip() or None,
            total_debit=float(row.get('total_debit', 0)),
            total_credit=float(row.get('total_credit', 0)),
            is_posted=bool(row.get('is_posted', False)),
        )
        return True
    
    # Helper methods
    def _add_error(self, row_number, column_name, error_type, message, raw_value=None, suggested_value=None):
        """Add an error to the errors list"""
        self.errors.append({
            'row_number': row_number,
            'column_name': column_name,
            'error_type': error_type,
            'error_message': message,
            'raw_value': raw_value,
            'suggested_value': suggested_value
        })
    
    def _add_log(self, level, message, details=None):
        """Add a log entry"""
        self.logs.append({
            'level': level,
            'message': message,
            'details': details
        })
    
    def _save_errors_and_logs(self):
        """Save errors and logs to database"""
        # Save errors
        for error_data in self.errors:
            ImportError.objects.create(
                data_import=self.data_import,
                **error_data
            )
        
        # Save logs
        for log_data in self.logs:
            ImportLog.objects.create(
                data_import=self.data_import,
                **log_data
            )


class TemplateService:
    """
    Service for managing import templates
    """
    
    @staticmethod
    def create_default_templates():
        """Create default import templates for all modules"""
        templates = [
            {
                'name': 'Customer Import Template',
                'template_type': 'CUSTOMERS',
                'description': 'Template for importing customer data',
                'required_columns': ['name', 'email'],
                'optional_columns': ['phone', 'address', 'city', 'state', 'postal_code', 'country'],
                'column_mappings': {
                    'name': 'name',
                    'email': 'email',
                    'phone': 'phone',
                    'address': 'address',
                    'city': 'city',
                    'state': 'state',
                    'postal_code': 'postal_code',
                    'country': 'country'
                },
                'validation_rules': {
                    'name': {'required': True, 'max_length': 255},
                    'email': {'required': True, 'format': 'email', 'unique': True}
                }
            },
            {
                'name': 'Supplier Import Template',
                'template_type': 'SUPPLIERS',
                'description': 'Template for importing supplier data',
                'required_columns': ['name', 'email'],
                'optional_columns': ['phone', 'address', 'city', 'state', 'postal_code', 'country'],
                'column_mappings': {
                    'name': 'name',
                    'email': 'email',
                    'phone': 'phone',
                    'address': 'address',
                    'city': 'city',
                    'state': 'state',
                    'postal_code': 'postal_code',
                    'country': 'country'
                },
                'validation_rules': {
                    'name': {'required': True, 'max_length': 255},
                    'email': {'required': True, 'format': 'email', 'unique': True}
                }
            },
            {
                'name': 'Product Import Template',
                'template_type': 'ITEMS',
                'description': 'Template for importing product/item data',
                'required_columns': ['name', 'sku', 'selling_price'],
                'optional_columns': ['description', 'cost_price', 'main_category', 'sub_category', 'unit_of_measure'],
                'column_mappings': {
                    'name': 'name',
                    'sku': 'sku',
                    'description': 'description',
                    'selling_price': 'selling_price',
                    'cost_price': 'cost_price',
                    'main_category': 'main_category',
                    'sub_category': 'sub_category',
                    'unit_of_measure': 'unit_of_measure'
                },
                'validation_rules': {
                    'name': {'required': True, 'max_length': 255},
                    'sku': {'required': True, 'unique': True, 'max_length': 100},
                    'selling_price': {'required': True, 'type': 'decimal', 'min_value': 0}
                }
            },
            {
                'name': 'Category Import Template',
                'template_type': 'CATEGORIES',
                'description': 'Template for importing category data',
                'required_columns': ['name'],
                'optional_columns': ['description'],
                'column_mappings': {
                    'name': 'name',
                    'description': 'description'
                },
                'validation_rules': {
                    'name': {'required': True, 'max_length': 255, 'unique': True}
                }
            },
            {
                'name': 'Location Import Template',
                'template_type': 'LOCATIONS',
                'description': 'Template for importing location data',
                'required_columns': ['name'],
                'optional_columns': ['address', 'city', 'state', 'postal_code', 'country'],
                'column_mappings': {
                    'name': 'name',
                    'address': 'address',
                    'city': 'city',
                    'state': 'state',
                    'postal_code': 'postal_code',
                    'country': 'country'
                },
                'validation_rules': {
                    'name': {'required': True, 'max_length': 255, 'unique': True}
                }
            },
            {
                'name': 'Inventory Import Template',
                'template_type': 'INVENTORY',
                'description': 'Template for importing initial inventory levels',
                'required_columns': ['product_sku', 'warehouse', 'quantity'],
                'optional_columns': [],
                'column_mappings': {
                    'product_sku': 'product_sku',
                    'warehouse': 'warehouse',
                    'quantity': 'quantity'
                },
                'validation_rules': {
                    'product_sku': {'required': True, 'foreign_key': 'Product'},
                    'warehouse': {'required': True, 'foreign_key': 'Warehouse'},
                    'quantity': {'required': True, 'type': 'decimal', 'min_value': 0}
                }
            },
            {
                'name': 'Sales Order Import Template',
                'template_type': 'SALES_ORDERS',
                'description': 'Template for importing sales orders',
                'required_columns': ['customer_id', 'order_date', 'total_amount'],
                'optional_columns': ['due_date', 'order_number', 'status', 'discount_amount', 'tax_amount', 'notes', 'shipping_address_line_1', 'shipping_city', 'shipping_state', 'shipping_postal_code', 'billing_address_line_1', 'billing_city', 'billing_state', 'billing_postal_code'],
                'column_mappings': {
                    'customer_id': 'customer_id',
                    'order_date': 'order_date',
                    'due_date': 'due_date',
                    'order_number': 'order_number',
                    'status': 'status',
                    'total_amount': 'total_amount',
                    'discount_amount': 'discount_amount',
                    'tax_amount': 'tax_amount',
                    'notes': 'notes'
                },
                'validation_rules': {
                    'customer_id': {'required': True, 'foreign_key': 'Customer'},
                    'order_date': {'required': True, 'type': 'date'},
                    'total_amount': {'required': True, 'type': 'decimal', 'min_value': 0}
                }
            },
            {
                'name': 'Invoice Import Template',
                'template_type': 'INVOICES',
                'description': 'Template for importing invoices',
                'required_columns': ['customer_id', 'invoice_date', 'total_amount'],
                'optional_columns': ['due_date', 'invoice_number', 'sales_order_number', 'status', 'amount_paid', 'balance_due', 'notes'],
                'column_mappings': {
                    'customer_id': 'customer_id',
                    'invoice_date': 'invoice_date',
                    'due_date': 'due_date',
                    'invoice_number': 'invoice_number',
                    'sales_order_number': 'sales_order_number',
                    'status': 'status',
                    'total_amount': 'total_amount',
                    'amount_paid': 'amount_paid',
                    'balance_due': 'balance_due',
                    'notes': 'notes'
                },
                'validation_rules': {
                    'customer_id': {'required': True, 'foreign_key': 'Customer'},
                    'invoice_date': {'required': True, 'type': 'date'},
                    'total_amount': {'required': True, 'type': 'decimal', 'min_value': 0}
                }
            },
            {
                'name': 'Payment Import Template',
                'template_type': 'PAYMENTS',
                'description': 'Template for importing customer payments',
                'required_columns': ['invoice_number', 'payment_date', 'amount'],
                'optional_columns': ['payment_method', 'transaction_id', 'notes'],
                'column_mappings': {
                    'invoice_number': 'invoice_number',
                    'payment_date': 'payment_date',
                    'amount': 'amount',
                    'payment_method': 'payment_method',
                    'transaction_id': 'transaction_id',
                    'notes': 'notes'
                },
                'validation_rules': {
                    'invoice_number': {'required': True, 'foreign_key': 'Invoice'},
                    'payment_date': {'required': True, 'type': 'date'},
                    'amount': {'required': True, 'type': 'decimal', 'min_value': 0}
                }
            },
            {
                'name': 'Purchase Order Import Template',
                'template_type': 'PURCHASE_ORDERS',
                'description': 'Template for importing purchase orders',
                'required_columns': ['supplier_id', 'order_date', 'total_amount'],
                'optional_columns': ['expected_delivery_date', 'order_number', 'status', 'notes'],
                'column_mappings': {
                    'supplier_id': 'supplier_id',
                    'order_date': 'order_date',
                    'expected_delivery_date': 'expected_delivery_date',
                    'order_number': 'order_number',
                    'status': 'status',
                    'total_amount': 'total_amount',
                    'notes': 'notes'
                },
                'validation_rules': {
                    'supplier_id': {'required': True, 'foreign_key': 'Supplier'},
                    'order_date': {'required': True, 'type': 'date'},
                    'total_amount': {'required': True, 'type': 'decimal', 'min_value': 0}
                }
            },
            {
                'name': 'Bill Import Template',
                'template_type': 'BILLS',
                'description': 'Template for importing supplier bills',
                'required_columns': ['supplier_id', 'bill_date', 'total_amount'],
                'optional_columns': ['due_date', 'bill_number', 'purchase_order_number', 'status', 'amount_paid', 'balance_due', 'notes'],
                'column_mappings': {
                    'supplier_id': 'supplier_id',
                    'bill_date': 'bill_date',
                    'due_date': 'due_date',
                    'bill_number': 'bill_number',
                    'purchase_order_number': 'purchase_order_number',
                    'status': 'status',
                    'total_amount': 'total_amount',
                    'amount_paid': 'amount_paid',
                    'balance_due': 'balance_due',
                    'notes': 'notes'
                },
                'validation_rules': {
                    'supplier_id': {'required': True, 'foreign_key': 'Supplier'},
                    'bill_date': {'required': True, 'type': 'date'},
                    'total_amount': {'required': True, 'type': 'decimal', 'min_value': 0}
                }
            },
            {
                'name': 'Supplier Payment Import Template',
                'template_type': 'SUPPLIER_PAYMENTS',
                'description': 'Template for importing supplier payments',
                'required_columns': ['bill_number', 'payment_date', 'amount'],
                'optional_columns': ['payment_method', 'transaction_id', 'notes'],
                'column_mappings': {
                    'bill_number': 'bill_number',
                    'payment_date': 'payment_date',
                    'amount': 'amount',
                    'payment_method': 'payment_method',
                    'transaction_id': 'transaction_id',
                    'notes': 'notes'
                },
                'validation_rules': {
                    'bill_number': {'required': True, 'foreign_key': 'Bill'},
                    'payment_date': {'required': True, 'type': 'date'},
                    'amount': {'required': True, 'type': 'decimal', 'min_value': 0}
                }
            },
            {
                'name': 'Account Import Template',
                'template_type': 'ACCOUNTS',
                'description': 'Template for importing chart of accounts',
                'required_columns': ['name', 'account_number', 'account_type'],
                'optional_columns': ['description', 'is_active'],
                'column_mappings': {
                    'name': 'name',
                    'account_number': 'account_number',
                    'account_type': 'account_type',
                    'description': 'description',
                    'is_active': 'is_active'
                },
                'validation_rules': {
                    'name': {'required': True, 'max_length': 255},
                    'account_number': {'required': True, 'unique': True, 'max_length': 20},
                    'account_type': {'required': True, 'choices': ['ASSET', 'LIABILITY', 'EQUITY', 'REVENUE', 'EXPENSE']}
                }
            },
            {
                'name': 'Journal Entry Import Template',
                'template_type': 'JOURNAL_ENTRIES',
                'description': 'Template for importing journal entries',
                'required_columns': ['entry_date', 'reference_number', 'total_debit', 'total_credit'],
                'optional_columns': ['entry_type', 'description', 'is_posted'],
                'column_mappings': {
                    'entry_date': 'entry_date',
                    'reference_number': 'reference_number',
                    'entry_type': 'entry_type',
                    'description': 'description',
                    'total_debit': 'total_debit',
                    'total_credit': 'total_credit',
                    'is_posted': 'is_posted'
                },
                'validation_rules': {
                    'entry_date': {'required': True, 'type': 'date'},
                    'reference_number': {'required': True, 'unique': True, 'max_length': 50},
                    'total_debit': {'required': True, 'type': 'decimal', 'min_value': 0},
                    'total_credit': {'required': True, 'type': 'decimal', 'min_value': 0}
                }
            }
        ]
        
        for template_data in templates:
            template, created = ImportTemplate.objects.get_or_create(
                name=template_data['name'],
                template_type=template_data['template_type'],
                defaults=template_data
            )
            if created:
                logger.info(f"Created template: {template.name}")

