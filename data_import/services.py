import pandas as pd
import json
from datetime import datetime
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from .models import ImportTemplate, DataImport, ImportErrorLog, ImportLog
from inventory.models import Product, Stock, Location, MainCategory, SubCategory
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
    
    def process_file(self):
        """Fungsi utama yang menjalankan validasi dan impor."""
        try:
            is_valid = self._validate_file()
            if is_valid:
                self._import_data()
            else:
                self.data_import.status = 'FAILED'
                self.data_import.notes = "File validation failed."
                self.data_import.completed_at = timezone.now()
                self.data_import.save(update_fields=['status', 'notes', 'completed_at'])
        except Exception as e:
            logger.error(f"Critical error during import {self.data_import.id}: {e}", exc_info=True)
            self.data_import.status = 'FAILED'
            self.data_import.notes = f"A critical error occurred: {str(e)}"
            self.data_import.completed_at = timezone.now()
            self.data_import.save()
            self._save_errors()
    
    def _validate_file(self):
        self.data_import.status = 'VALIDATING'
        self.data_import.started_at = timezone.now()
        self.data_import.save()
        self._add_log('INFO', f"Starting validation for file: {self.data_import.file.name}")

        converters = {'code': str}

        try:
            df = pd.read_excel(
                self.data_import.file.path, 
                dtype=str, # Tetap gunakan dtype=str sebagai pertahanan utama
                converters=converters
            ).fillna('')
        except Exception:
            try:
                df = pd.read_csv(
                    self.data_import.file.path, 
                    dtype=str, 
                    converters=converters
                ).fillna('')
            except Exception as e:
                self._add_error(0, f"Could not read file. Error: {e}")
                return False
        
        self.data_import.total_rows = len(df)
        
        # Validasi kolom wajib dari template
        required_columns = self.template.required_columns
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            msg = f"Missing required columns: {', '.join(missing_columns)}"
            self._add_error(0, msg) # Gunakan _add_error yang sudah diperbaiki
            self._add_log('CRITICAL', msg) # Log sebagai critical
            return False

        # Dapatkan fungsi validator berdasarkan template_type
        validator = self._get_validator()
        if not validator:
            self._add_error(0, f"No validator found for template type '{self.template.template_type}'")
            return False

        for index, row in df.iterrows():
            self._add_log('DEBUG', f"Validating row {index + 2}", row.to_dict())
            if not validator(index + 2, row):
                self.data_import.failed_rows += 1
        
        self._save_errors()
        self._save_logs() # Simpan log
        self.data_import.save()
        
        if self.data_import.failed_rows > 0:
            self._add_log('WARNING', f"Validation completed with {self.data_import.failed_rows} errors.")
        else:
            self._add_log('INFO', "Validation completed successfully.")
            
        return self.data_import.failed_rows == 0

    def _import_data(self):
        self.data_import.status = 'PROCESSING'
        self.data_import.save()

        df = pd.read_excel(self.data_import.file.path, dtype=str).fillna('')
        importer = self._get_importer()

        for index, row in df.iterrows():
            try:
                with transaction.atomic():
                    if importer(index + 2, row):
                        self.data_import.successful_rows += 1
            except Exception as e:
                self._add_error(index + 2, f"Import failed: {str(e)}", row.to_dict())
                self.data_import.failed_rows += 1
        
        self.data_import.processed_rows = self.data_import.total_rows
        self.data_import.status = 'COMPLETED' if self.data_import.failed_rows == 0 else 'COMPLETED_WITH_ERRORS'
        self.data_import.completed_at = timezone.now()
        self.data_import.save()
        self._save_errors()

    # --- Helper dan Dispatcher ---
    def _add_error(self, row_number, message, raw_data=None):
        """Menambahkan error dan juga mencatatnya sebagai log."""
        error_details = {
            'row': row_number,
            'data': raw_data
        }
        # Catat sebagai log level ERROR
        self._add_log('ERROR', message, details=error_details)
        
        # Tambahkan ke daftar error untuk disimpan ke ImportErrorLog
        self.errors.append(ImportErrorLog(
            data_import=self.data_import,
            row_number=row_number,
            error_message=message,
            raw_data=raw_data
        ))

    def _save_errors(self):
        if self.errors:
            ImportErrorLog.objects.bulk_create(self.errors)
            self.errors = []

    def _save_logs(self):
        """Menyimpan semua log yang terkumpul."""
        if self.logs:
            ImportLog.objects.bulk_create(self.logs)
            self.logs = []

    def _get_validator(self):
        return getattr(self, f"_validate_{self.template.template_type.lower()}_row", None)

    def _get_importer(self):
        return getattr(self, f"_import_{self.template.template_type.lower()}_row", None)

    # --- Logika Spesifik per Tipe ---
    
    # PRODUCTS
    def _validate_products_row(self, row_number, row):
        is_valid = True
        if not row.get('sku'):
            self._add_error(row_number, "SKU is required.", row.to_dict())
            is_valid = False
        elif Product.objects.filter(sku=row['sku']).exists():
            self._add_error(row_number, f"Product with SKU '{row['sku']}' already exists.", row.to_dict())
            is_valid = False
        return is_valid

    def _import_products_row(self, row_number, row):
        Product.objects.create(
            sku=row['sku'],
            name=row['name'],
            color=row.get('color', ''),
            cost_price=float(row.get('cost_price', 0)) if row.get('cost_price') else 0,
            selling_price=float(row.get('selling_price', 0)) if row.get('selling_price') else 0,
            main_category_id=int(row['main_category_id']) if row.get('main_category_id') else None,
            sub_category_id=int(row['sub_category_id']) if row.get('sub_category_id') else None,
        )
        return True

    # CUSTOMERS
    def _validate_customers_row(self, row_number, row):
        is_valid = True
        # if not row.get('email'):
        #     self._add_error(row_number, "Email is required.", row.to_dict())
        #     is_valid = False
        # elif Customer.objects.filter(email=row['email']).exists():
        #     self._add_error(row_number, f"Customer with email '{row['email']}' already exists.", row.to_dict())
        #     is_valid = False
        return is_valid

    def _import_customers_row(self, row_number, row):
        Customer.objects.create(
            name=row['name'], 
            phone=row.get('phone', ''),
            mobile=row.get('mobile', ''),
            payment_type=row.get('payment_type'),
            payment_terms=row.get('payment_terms'),
            credit_limit=row.get('credit_limit'),
            address_line_1=row.get('address_line_1'),
            city=row.get('city'),
            state=row.get('state'),
            notes=row.get('notes'),
            customer_group_id=row.get('customer_group_id')
        )
        return True
    
    # Supplier validation and import methods
    def _validate_suppliers_row(self, row_number, row):
        """Validate supplier data"""
        is_valid = True
        
        if pd.isna(row.get('name')) or not str(row.get('name')).strip():
            self._add_error(row_number, 'name', 'VALIDATION_ERROR', 'Supplier name is required')
            is_valid = False
        
        # if pd.isna(row.get('email')) or not str(row.get('email')).strip():
        #     self._add_error(row_number, 'email', 'VALIDATION_ERROR', 'Supplier email is required')
        #     is_valid = False
        # else:
        #     email = str(row.get('email')).strip()
        #     if Supplier.objects.filter(email=email).exists():
        #         self._add_error(row_number, 'email', 'DUPLICATE_VALUE', f'Supplier with email {email} already exists')
        #         is_valid = False
        
        return is_valid
    
    def _import_suppliers_row(self, row_number, row):
        """Import supplier data"""
        supplier = Supplier.objects.create(
            name=str(row.get('name')).strip(),
            contact_person=str(row.get('contact_person', '')).strip() or None,
            phone=str(row.get('phone', '')).strip() or None,
            full_address=str(row.get('address', '')).strip() or None, 
            currency=str(row.get('currency', 'IDR')).strip() or 'IDR',
            payment_terms=str(row.get('payment_terms', '')).strip() or None,
        )

        # Langkah 2: Setelah objek dibuat, 'supplier.id' sekarang memiliki nilai.
        # Kita gunakan nilai ini untuk membuat supplier_id yang diformat.
        # 'S' + padding nol di kiri hingga total 4 digit. Contoh: 45 -> S0045
        formatted_id = f"S{str(supplier.id).zfill(4)}"
        
        # Langkah 3: Tetapkan supplier_id yang baru dibuat ke objek.
        supplier.supplier_id = formatted_id
        
        # Langkah 4: Simpan kembali objek untuk memperbarui field supplier_id di database.
        # Kita hanya memperbarui field ini untuk efisiensi.
        supplier.save(update_fields=['supplier_id'])

        return True
    
    # Product validation and import methods
    def _validate_product_row(self, row_number, row):
        """Validate product data"""
        is_valid = True
        
        # Check required fields
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
        
        # Validate Main Category
        main_category_name = row.get('main_category')
        if main_category_name and not pd.isna(main_category_name):
            try:
                MainCategory.objects.get(name=str(main_category_name).strip())
            except MainCategory.DoesNotExist:
                self._add_error(row_number, 'main_category', 'FOREIGN_KEY_ERROR', f'Main Category "{main_category_name}" does not exist')
                is_valid = False
        
        # Validate Sub Category
        sub_category_name = row.get('sub_category')
        if sub_category_name and not pd.isna(sub_category_name):
            try:
                SubCategory.objects.get(name=str(sub_category_name).strip())
            except SubCategory.DoesNotExist:
                self._add_error(row_number, 'sub_category', 'FOREIGN_KEY_ERROR', f'Sub Category "{sub_category_name}" does not exist')
                is_valid = False
        
        # Validate selling_price
        try:
            selling_price = float(row.get('selling_price', 0))
            if selling_price < 0:
                self._add_error(row_number, 'selling_price', 'VALIDATION_ERROR', 'Selling price cannot be negative')
                is_valid = False
        except (ValueError, TypeError):
            self._add_error(row_number, 'selling_price', 'DATA_TYPE_ERROR', 'Invalid selling price format')
            is_valid = False
            
        # Validate cost_price
        cost_price = row.get('cost_price')
        if cost_price and not pd.isna(cost_price):
            try:
                cost_price = float(cost_price)
                if cost_price < 0:
                    self._add_error(row_number, 'cost_price', 'VALIDATION_ERROR', 'Cost price cannot be negative')
                    is_valid = False
            except (ValueError, TypeError):
                self._add_error(row_number, 'cost_price', 'DATA_TYPE_ERROR', 'Invalid cost price format')
                is_valid = False
        
        # Validate numeric fields (minimum_stock_level, maximum_stock_level, reorder_point, weight)
        numeric_fields = ['minimum_stock_level', 'maximum_stock_level', 'reorder_point', 'weight', 'discount']
        for field in numeric_fields:
            value = row.get(field)
            if value and not pd.isna(value):
                try:
                    float(value)
                except (ValueError, TypeError):
                    self._add_error(row_number, field, 'DATA_TYPE_ERROR', f'Invalid numeric format for {field}')
                    is_valid = False
        
        return is_valid

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
            discount=float(row.get('discount', 0.00)) if row.get('discount') and not pd.isna(row.get('discount')) else 0.00,
            main_category=main_category,
            sub_category=sub_category,
            color=str(row.get('color', '')).strip() or None,
            size=str(row.get('size', '')).strip() or None,
            brand=str(row.get('brand', '')).strip() or None,
            model=str(row.get('model', '')).strip() or None,
            unit_of_measure=str(row.get('unit_of_measure', 'pcs')).strip(),
            weight=float(row.get('weight')) if row.get('weight') and not pd.isna(row.get('weight')) else None,
            dimensions=str(row.get('dimensions', '')).strip() or None,
            is_active=row.get('is_active', True),
            is_sellable=row.get('is_sellable', True),
            is_purchasable=row.get('is_purchasable', True),
            is_manufactured=row.get('is_manufactured', False),
            minimum_stock_level=float(row.get('minimum_stock_level', 0)) if row.get('minimum_stock_level') and not pd.isna(row.get('minimum_stock_level')) else 0,
            maximum_stock_level=float(row.get('maximum_stock_level')) if row.get('maximum_stock_level') and not pd.isna(row.get('maximum_stock_level')) else None,
            reorder_point=float(row.get('reorder_point', 0)) if row.get('reorder_point') and not pd.isna(row.get('reorder_point')) else 0,
            barcode=str(row.get('barcode', '')).strip() or None,
            supplier_code=str(row.get('supplier_code', '')).strip() or None,
            notes=str(row.get('notes', '')).strip() or None,
        )
        return True
    
    # MainCategory validation and import methods
    def _validate_main_category_row(self, row_number, row):
        """Validate main category data"""
        is_valid = True
        
        if pd.isna(row.get('name')) or not str(row.get('name')).strip():
            self._add_error(row_number, 'name', 'VALIDATION_ERROR', 'Main Category name is required')
            is_valid = False
        else:
            name = str(row.get('name')).strip()
            if MainCategory.objects.filter(name=name).exists():
                self._add_error(row_number, 'name', 'DUPLICATE_VALUE', f'Main Category with name {name} already exists')
                is_valid = False
        
        return is_valid
    
    def _import_main_category_row(self, row_number, row):
        """Import main category data"""
        MainCategory.objects.create(
            name=str(row.get('name')).strip(),
            description=str(row.get('description', '')).strip() or None,
            is_active=row.get('is_active', True)
        )
        return True

    # SubCategory validation and import methods
    def _validate_sub_category_row(self, row_number, row):
        """Validate sub category data"""
        is_valid = True
        
        if pd.isna(row.get('name')) or not str(row.get('name')).strip():
            self._add_error(row_number, 'name', 'VALIDATION_ERROR', 'Sub Category name is required')
            is_valid = False
        else:
            name = str(row.get('name')).strip()
            if SubCategory.objects.filter(name=name).exists():
                self._add_error(row_number, 'name', 'DUPLICATE_VALUE', f'Sub Category with name {name} already exists')
                is_valid = False
        
        return is_valid
    
    def _import_sub_category_row(self, row_number, row):
        """Import sub category data"""
        SubCategory.objects.create(
            name=str(row.get('name')).strip(),
            description=str(row.get('description', '')).strip() or None,
            is_active=row.get('is_active', True)
        )
        return True
    
    # Category (Linker) validation and import methods
    def _validate_category_row(self, row_number, row):
        """Validate Category (Linker) data"""
        is_valid = True
        
        # Check required fields
        if pd.isna(row.get('name')) or not str(row.get('name')).strip():
            self._add_error(row_number, 'name', 'VALIDATION_ERROR', 'Category name is required')
            is_valid = False
        
        # Validate Main Category
        main_category_name = row.get('main_category')
        if pd.isna(main_category_name) or not str(main_category_name).strip():
            self._add_error(row_number, 'main_category', 'VALIDATION_ERROR', 'Main Category is required')
            is_valid = False
        else:
            try:
                MainCategory.objects.get(name=str(main_category_name).strip())
            except MainCategory.DoesNotExist:
                self._add_error(row_number, 'main_category', 'FOREIGN_KEY_ERROR', f'Main Category "{main_category_name}" does not exist')
                is_valid = False
        
        # Validate Sub Category
        sub_category_name = row.get('sub_category')
        if pd.isna(sub_category_name) or not str(sub_category_name).strip():
            self._add_error(row_number, 'sub_category', 'VALIDATION_ERROR', 'Sub Category is required')
            is_valid = False
        else:
            try:
                SubCategory.objects.get(name=str(sub_category_name).strip())
            except SubCategory.DoesNotExist:
                self._add_error(row_number, 'sub_category', 'FOREIGN_KEY_ERROR', f'Sub Category "{sub_category_name}" does not exist')
                is_valid = False
        
        # Check for unique_together: ("main_category", "sub_category")
        if is_valid:
            main_cat = MainCategory.objects.get(name=str(main_category_name).strip())
            sub_cat = SubCategory.objects.get(name=str(sub_category_name).strip())
            if Category.objects.filter(main_category=main_cat, sub_category=sub_cat).exists():
                self._add_error(row_number, 'main_category/sub_category', 'DUPLICATE_VALUE', f'Category link between "{main_category_name}" and "{sub_category_name}" already exists')
                is_valid = False
        
        return is_valid
    
    def _import_category_row(self, row_number, row):
        """Import Category (Linker) data"""
        main_category = MainCategory.objects.get(name=str(row.get('main_category')).strip())
        sub_category = SubCategory.objects.get(name=str(row.get('sub_category')).strip())
        
        Category.objects.create(
            name=str(row.get('name')).strip(),
            main_category=main_category,
            sub_category=sub_category,
            description=str(row.get('description', '')).strip() or None,
            is_active=row.get('is_active', True)
        )
        return True
    
    # Location validation and import methods
    def _validate_location_row(self, row_number, row):
        """Validate location data"""
        is_valid = True
        
        if pd.isna(row.get('name')) or not str(row.get('name')).strip():
            self._add_error(row_number, 'name', 'VALIDATION_ERROR', 'Location name is required')
            is_valid = False
        
        if pd.isna(row.get('code')) or not str(row.get('code')).strip():
            self._add_error(row_number, 'code', 'VALIDATION_ERROR', 'Location code is required')
            is_valid = False
        else:
            code = str(row.get('code')).strip()
            if Location.objects.filter(code=code).exists():
                self._add_error(row_number, 'code', 'DUPLICATE_VALUE', f'Location with code {code} already exists')
                is_valid = False
        
        # Validate location_type
        location_type = str(row.get('location_type', 'WAREHOUSE')).strip().upper()
        valid_types = [choice[0] for choice in Location.LOCATION_TYPES]
        if location_type not in valid_types:
            self._add_error(row_number, 'location_type', 'VALIDATION_ERROR', f'Invalid location type: {location_type}. Must be one of {", ".join(valid_types)}')
            is_valid = False
            
        # Validate numeric fields (storage_capacity, current_utilization)
        numeric_fields = ['storage_capacity', 'current_utilization']
        for field in numeric_fields:
            value = row.get(field)
            if value and not pd.isna(value):
                try:
                    float(value)
                except (ValueError, TypeError):
                    self._add_error(row_number, field, 'DATA_TYPE_ERROR', f'Invalid numeric format for {field}')
                    is_valid = False
        
        return is_valid
    
    def _import_location_row(self, row_number, row):
        """Import location data"""
        Location.objects.create(
            name=str(row.get('name')).strip(),
            code=str(row.get('code')).strip(),
            location_type=str(row.get('location_type', 'WAREHOUSE')).strip().upper(),
            address=str(row.get('address', '')).strip() or None,
            contact_person=str(row.get('contact_person', '')).strip() or None,
            phone=str(row.get('phone', '')).strip() or None,
            email=str(row.get('email', '')).strip() or None,
            is_active=row.get('is_active', True),
            is_sellable_location=row.get('is_sellable_location', True),
            is_purchasable_location=row.get('is_purchasable_location', True),
            is_manufacturing_location=row.get('is_manufacturing_location', False),
            storage_capacity=float(row.get('storage_capacity')) if row.get('storage_capacity') and not pd.isna(row.get('storage_capacity')) else None,
            current_utilization=float(row.get('current_utilization', 0.00)) if row.get('current_utilization') and not pd.isna(row.get('current_utilization')) else 0.00,
            notes=str(row.get('notes', '')).strip() or None,
        )
        return True
    
    # Inventory validation and import methods
    def _validate_inventory_row(self, row_number, row):
        is_valid = True
        if not row.get('product_sku'):
            self._add_error(row_number, "Product SKU is required.", row.to_dict())
            is_valid = False
        else:
            try:
                Product.objects.get(sku=row['product_sku'])
            except Product.DoesNotExist:
                self._add_error(row_number, f"Product with SKU '{row['product_sku']}' not found.", row.to_dict())
                is_valid = False
        
        location_code = row.get('warehouse_code')

        if not location_code:
            self._add_error(row_number, "Location Code is required.", row.to_dict())
            is_valid = False
        else:
            try:
                Location.objects.get(code=location_code)
            except Location.DoesNotExist:
                self._add_error(row_number, f"Location with code '{row['location_code']}' not found.", row.to_dict())
                is_valid = False
        
        try:
            float(row.get('quantity_on_hand', 0))
        except (ValueError, TypeError):
            self._add_error(row_number, "Invalid format for quantity_on_hand. Must be a number.", row.to_dict())
            is_valid = False
            
        return is_valid
    
    def _import_inventory_row(self, row_number, row):
        product = Product.objects.get(sku=row['product_sku'])
        location = Location.objects.get(code=row['warehouse_code'])
        quantity = row.get('quantity_on_hand', 0)

        stock, created = Stock.objects.get_or_create(
            product=product,
            location=location,
            defaults={'quantity_on_hand': quantity, 'quantity_sellable': quantity}
        )
        if not created:
            stock.quantity_on_hand = quantity
            stock.quantity_sellable = quantity
            stock.save()
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
    def _validate_accounts_row(self, row_number, row):
        """Validate account data"""
        is_valid = True
        
        #Validate account name
        if pd.isna(row.get('name')) or not str(row.get('name')).strip():
            self._add_error(row_number, 'name', 'VALIDATION_ERROR', 'Account name is required')
            is_valid = False
        
        # Validate account number
        account_number = row.get('code')
        if pd.isna(account_number) or not str(account_number).strip():
            self._add_error(row_number, 'Account code is required', row.to_dict())
            is_valid = False
        else:
            account_code_str = str(account_number).strip()
            self._add_log('DEBUG', f"Checking for existing account with code: {account_code_str}")
            if Account.objects.filter(code=account_code_str).exists():
                self._add_error(row_number, f'Account with code {account_code_str} already exists', row.to_dict())
                is_valid = False
        
        # Validate account type
        account_type_name = row.get('account_type_name') # Ganti nama kolom sesuai file Excel Anda
        if pd.isna(account_type_name) or not str(account_type_name).strip():
            self._add_error(row_number, 'Account type name is required', row.to_dict())
            is_valid = False
        else:
            from accounting.models import AccountType
            try:
                # Coba cari AccountType berdasarkan nama
                AccountType.objects.get(name__iexact=str(account_type_name).strip())
                self._add_log('DEBUG', f"Found valid AccountType: {account_type_name}")
            except AccountType.DoesNotExist:
                self._add_error(row_number, f'AccountType with name "{account_type_name}" does not exist.', row.to_dict())
                is_valid = False
        
        if not is_valid:
            self._add_log('WARNING', f"Row {row_number} failed validation.")
        
        return is_valid
    
    def _import_accounts_row(self, row_number, row):
        """Import account data"""
        from accounting.models import AccountType
        account_type_name = row.get('account_type_name') # Pastikan nama kolom ini sesuai dengan file Excel Anda
        account_type_obj = AccountType.objects.get(name__iexact=str(account_type_name).strip())

        # Dapatkan objek parent account jika ada
        parent_account_obj = None
        parent_code = row.get('parent_account_code') # Asumsi ada kolom 'parent_account_code'
        if parent_code and not pd.isna(parent_code):
            try:
                parent_account_obj = Account.objects.get(code=str(parent_code).strip())
            except Account.DoesNotExist:
                # Anda bisa menambahkan error di sini jika parent tidak ditemukan
                self._add_error(row_number, f"Parent account with code '{parent_code}' not found.", row.to_dict())
                return False # Hentikan impor baris ini

        account = Account.objects.create(
            name=str(row.get('name')).strip(),
            code=str(row.get('code')).strip(),
            account_type=account_type_obj, # Gunakan objek yang sudah ditemukan
            description=str(row.get('description', '')).strip() or None,
            is_active=bool(row.get('is_active', True)),
            parent_account=parent_account_obj, # Gunakan objek parent
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
    
    def _add_log(self, level, message, details=None):
        """Menambahkan log ke dalam list untuk disimpan nanti."""
        print(f"LOG [{level}] - {message} - Details: {details}") # Untuk debugging langsung di konsol server
        self.logs.append(ImportLog(
            data_import=self.data_import,
            level=level.upper(), # 'INFO', 'WARNING', 'ERROR'
            message=message,
            details=json.dumps(details) if details else None
        ))
    
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

