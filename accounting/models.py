from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from common.models import BaseModel
from django.conf import settings
from inventory.models import Location

class AccountType(models.Model):
    """
    Account Types for Chart of Accounts
    """
    ACCOUNT_CATEGORIES = [
        ('ASSET', 'Asset'),
        ('LIABILITY', 'Liability'), 
        ('EQUITY', 'Equity'),
        ('REVENUE', 'Revenue'),
        ('EXPENSE', 'Expense'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=20, choices=ACCOUNT_CATEGORIES)
    code_prefix = models.CharField(max_length=10, unique=True, help_text="Prefix for account codes (e.g., 1 for Assets)")
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Account Type"
        verbose_name_plural = "Account Types"
        db_table = "accounting_account_types"
        ordering = ['code_prefix', 'name']

    def __str__(self):
        return f"{self.code_prefix} - {self.name}"

class Account(BaseModel):
    """
    Chart of Accounts - Bagan Akun
    """
    account_type = models.ForeignKey(AccountType, on_delete=models.PROTECT, related_name='accounts')
    code = models.CharField(max_length=20, unique=True, db_index=True, default='0000')
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True, null=True)
    parent_account = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='sub_accounts')
    
    # Account Properties
    is_active = models.BooleanField(default=True)
    is_header_account = models.BooleanField(default=False, help_text="Header accounts cannot have transactions")
    allow_manual_entries = models.BooleanField(default=True, help_text="Allow manual journal entries")
    
    # Balance Information
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    current_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    # Additional Properties
    tax_account = models.BooleanField(default=False, help_text="Is this a tax-related account?")
    bank_account = models.BooleanField(default=False, help_text="Is this a bank account?")
    cash_account = models.BooleanField(default=False, help_text="Is this a cash account?")
    
    notes = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Account"
        verbose_name_plural = "Chart of Accounts"
        db_table = "accounting_accounts"
        ordering = ['code']
        indexes = [
            models.Index(fields=['account_type', 'is_active']),
            models.Index(fields=['code']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def full_name(self):
        if self.parent_account:
            return f"{self.parent_account.name} > {self.name}"
        return self.name

    @property
    def account_category(self):
        return self.account_type.category

    def clean(self):
        if self.is_header_account and self.parent_account:
            if self.parent_account.is_header_account:
                raise ValidationError("Header account cannot have another header account as parent")

    def get_balance(self, as_of_date=None):
        """Get account balance as of specific date"""
        if as_of_date is None:
            as_of_date = timezone.now().date()
        
        entries = JournalEntryLine.objects.filter(
            account=self,
            journal_entry__entry_date__lte=as_of_date,
            journal_entry__status='POSTED'
        )
        
        debit_total = sum(entry.debit_amount for entry in entries)
        credit_total = sum(entry.credit_amount for entry in entries)
        
        # Calculate balance based on account type
        if self.account_type.category in ['ASSET', 'EXPENSE']:
            return self.opening_balance + debit_total - credit_total
        else:  # LIABILITY, EQUITY, REVENUE
            return self.opening_balance + credit_total - debit_total

class JournalEntry(BaseModel):
    """
    Journal Entries - Jurnal Umum
    """
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('POSTED', 'Posted'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    ENTRY_TYPES = [
        ('MANUAL', 'Manual Entry'),
        ('SALES', 'Sales Transaction'),
        ('PURCHASE', 'Purchase Transaction'),
        ('INVENTORY', 'Inventory Adjustment'),
        ('PAYMENT', 'Payment'),
        ('RECEIPT', 'Receipt'),
        ('ADJUSTMENT', 'Adjustment'),
        ('CLOSING', 'Closing Entry'),
    ]

    entry_number = models.CharField(max_length=50, unique=True, db_index=True)
    entry_date = models.DateField(default=timezone.now)
    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPES, default='MANUAL')
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField()
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    posted_date = models.DateTimeField(null=True, blank=True)
    
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, # <-- UBAH INI
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='posted_journal_entries'
    )
    
    total_debit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_credit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    # Source document references
    sales_order = models.ForeignKey('sales.SalesOrder', on_delete=models.SET_NULL, null=True, blank=True)
    purchase_order = models.ForeignKey('purchasing.PurchaseOrder', on_delete=models.SET_NULL, null=True, blank=True)
    goods_receipt = models.ForeignKey('inventory.GoodsReceipt', on_delete=models.SET_NULL, null=True, blank=True)
    
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_journal_entries'
    )

    class Meta:
        verbose_name = "Journal Entry"
        verbose_name_plural = "Journal Entries"
        db_table = "accounting_journal_entries"
        ordering = ['-entry_date', '-created_at']

    def __str__(self):
        return f"{self.entry_number} - {self.description}"

    def save(self, *args, **kwargs):
        if not self.entry_number:
            # Generate entry number
            today = timezone.now().date()
            prefix = f"JE{today.strftime('%Y%m')}"
            last_entry = JournalEntry.objects.filter(
                entry_number__startswith=prefix
            ).order_by('-entry_number').first()
            
            if last_entry:
                last_number = int(last_entry.entry_number[-4:])
                new_number = last_number + 1
            else:
                new_number = 1
            
            self.entry_number = f"{prefix}{new_number:04d}"
        
        super().save(*args, **kwargs)

    def clean(self):
        if self.status == 'POSTED' and abs(self.total_debit - self.total_credit) > 0.01:
            raise ValidationError("Total debit must equal total credit for posted entries")

    def post_entry(self, user):
        """Post the journal entry and update account balances"""
        if self.status != 'DRAFT':
            raise ValidationError("Only draft entries can be posted")
        
        # Validate that debits equal credits
        if abs(self.total_debit - self.total_credit) > 0.01:
            raise ValidationError("Total debit must equal total credit")
        
        # Update account balances
        for line in self.lines.all():
            account = line.account
            if account.account_type.category in ['ASSET', 'EXPENSE']:
                account.current_balance += line.debit_amount - line.credit_amount
            else:  # LIABILITY, EQUITY, REVENUE
                account.current_balance += line.credit_amount - line.debit_amount
            account.save()
        
        # Update entry status
        self.status = 'POSTED'
        self.posted_date = timezone.now()
        self.posted_by = user
        self.save()

class JournalEntryLine(BaseModel):
    """
    Journal Entry Lines - Detail Jurnal
    """
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    description = models.CharField(max_length=255, blank=True, null=True)
    
    debit_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    credit_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    # Additional references
    reference_id = models.CharField(max_length=100, blank=True, null=True)
    reference_type = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        verbose_name = "Journal Entry Line"
        verbose_name_plural = "Journal Entry Lines"
        db_table = "accounting_journal_entry_lines"

    def __str__(self):
        return f"{self.journal_entry.entry_number} - {self.account.name}"

    def clean(self):
        if self.debit_amount > 0 and self.credit_amount > 0:
            raise ValidationError("A line cannot have both debit and credit amounts")
        if self.debit_amount == 0 and self.credit_amount == 0:
            raise ValidationError("A line must have either debit or credit amount")

class FiscalYear(BaseModel):
    """
    Fiscal Year for accounting periods
    """
    name = models.CharField(max_length=100, unique=True)
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)
    is_closed = models.BooleanField(default=False)
    closed_date = models.DateTimeField(null=True, blank=True)
    
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, # <-- UBAH INI
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='closed_fiscal_years'
    )

    class Meta:
        verbose_name = "Fiscal Year"
        verbose_name_plural = "Fiscal Years"
        db_table = "accounting_fiscal_years"
        ordering = ['-start_date']

    def __str__(self):
        return self.name

    def clean(self):
        if self.start_date >= self.end_date:
            raise ValidationError("Start date must be before end date")

class AccountingPeriod(BaseModel):
    """
    Accounting Periods (Monthly)
    """
    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.CASCADE, related_name='periods')
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    is_closed = models.BooleanField(default=False)
    closed_date = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, # <-- UBAH INI
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='closed_periods'
    )

    class Meta:
        verbose_name = "Accounting Period"
        verbose_name_plural = "Accounting Periods"
        db_table = "accounting_periods"
        unique_together = ['fiscal_year', 'name']
        ordering = ['start_date']

    def __str__(self):
        return f"{self.fiscal_year.name} - {self.name}"

class TaxRate(BaseModel):
    """
    Tax Rates for different types of taxes
    """
    TAX_TYPES = [
        ('VAT', 'Value Added Tax (PPN)'),
        ('INCOME', 'Income Tax (PPh)'),
        ('SALES', 'Sales Tax'),
        ('WITHHOLDING', 'Withholding Tax'),
    ]

    name = models.CharField(max_length=100)
    tax_type = models.CharField(max_length=20, choices=TAX_TYPES)
    rate = models.DecimalField(max_digits=5, decimal_places=2, help_text="Tax rate as percentage")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, help_text="Account to post tax amounts")
    is_active = models.BooleanField(default=True)
    effective_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Tax Rate"
        verbose_name_plural = "Tax Rates"
        db_table = "accounting_tax_rates"
        ordering = ['tax_type', 'name']

    def __str__(self):
        return f"{self.name} ({self.rate}%)"

class BankAccount(BaseModel):
    """
    Bank Account Management
    """
    account = models.OneToOneField(Account, on_delete=models.CASCADE, related_name='bank_details')
    bank_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=50)
    account_holder = models.CharField(max_length=255)
    branch = models.CharField(max_length=255, blank=True, null=True)
    swift_code = models.CharField(max_length=20, blank=True, null=True)
    iban = models.CharField(max_length=50, blank=True, null=True)
    currency = models.CharField(max_length=3, default='IDR')
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Bank Account"
        verbose_name_plural = "Bank Accounts"
        db_table = "accounting_bank_accounts"

    def __str__(self):
        return f"{self.bank_name} - {self.account_number}"

# Keep legacy models for backward compatibility
class JournalItem(BaseModel):
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="items")
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Journal Item"
        verbose_name_plural = "Journal Items"
        db_table = "accounting_journal_items"

    def __str__(self):
        return f"{self.account.name}: Debit {self.debit}, Credit {self.credit}"

class Ledger(BaseModel):
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    journal_item = models.ForeignKey(JournalItem, on_delete=models.PROTECT)
    date = models.DateField()
    description = models.TextField(blank=True, null=True)
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    class Meta:
        verbose_name = "Ledger Entry"
        verbose_name_plural = "Ledger Entries"
        db_table = "accounting_ledgers"
        ordering = ["date", "-created_at"]

    def __str__(self):
        return f"Ledger for {self.account.name} on {self.date}"

class AssetCategory(BaseModel):
    """Kategori Aset, misal: Kendaraan, Elektronik, Mesin, Properti."""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    
    # Akun terkait untuk jurnal otomatis
    asset_account = models.ForeignKey(Account, related_name='asset_categories', on_delete=models.PROTECT, help_text="Akun Aset Tetap di neraca (e.g., '1-2100 Kendaraan')")
    accumulated_depreciation_account = models.ForeignKey(Account, related_name='asset_cat_acc_dep', on_delete=models.PROTECT, help_text="Akun Akumulasi Penyusutan (e.g., '1-2101 Akum. Peny. Kendaraan')")
    depreciation_expense_account = models.ForeignKey(Account, related_name='asset_cat_dep_exp', on_delete=models.PROTECT, help_text="Akun Beban Penyusutan di laba rugi (e.g., '6-1500 Beban Peny. Kendaraan')")

    class Meta:
        verbose_name = "Asset Category"
        verbose_name_plural = "Asset Categories"
        db_table = "accounting_asset_categories" # Beri nama tabel yang jelas

    def __str__(self):
        return self.name

class Asset(BaseModel):
    """Model utama untuk Aset Tetap."""
    STATUS_CHOICES = [
        ('IN_USE', 'In Use'),
        ('IN_REPAIR', 'In Repair'),
        ('IDLE', 'Idle'),
        ('DISPOSED', 'Disposed'),
    ]
    
    asset_code = models.CharField(max_length=50, unique=True, blank=True)
    name = models.CharField(max_length=255)
    category = models.ForeignKey(AssetCategory, on_delete=models.PROTECT, related_name="assets")
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name="assets")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IN_USE')

    # Info Perolehan
    purchase_date = models.DateField()
    purchase_price = models.DecimalField(max_digits=15, decimal_places=2)
    
    # Info Penyusutan
    depreciation_method = models.CharField(max_length=20, default='STRAIGHT_LINE')
    useful_life_months = models.PositiveIntegerField(help_text="Masa manfaat dalam bulan")
    salvage_value = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Nilai sisa di akhir masa manfaat")
    
    # Info Pelepasan
    disposal_date = models.DateField(null=True, blank=True)
    disposal_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "Asset"
        verbose_name_plural = "Assets"
        db_table = "accounting_assets"

    def __str__(self):
        return f"{self.asset_code} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.asset_code:
            prefix = f"ASSET-{self.purchase_date.year}-"
            last_asset = Asset.objects.filter(asset_code__startswith=prefix).order_by('asset_code').last()
            if last_asset:
                last_num = int(last_asset.asset_code.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            self.asset_code = f"{prefix}{new_num:04d}"
        super().save(*args, **kwargs)

class AssetDepreciation(BaseModel):
    """Mencatat setiap penyusutan yang terjadi per aset per periode."""
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='depreciations')
    period_date = models.DateField(help_text="Tanggal akhir periode penyusutan (e.g., akhir bulan)")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    journal_entry = models.OneToOneField(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name="asset_depreciation")

    class Meta:
        unique_together = ('asset', 'period_date')
        db_table = "accounting_asset_depreciations"

class AssetMaintenance(BaseModel):
    """Mencatat riwayat pemeliharaan aset."""
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='maintenances')
    maintenance_date = models.DateField()
    description = models.TextField()
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    performed_by = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "accounting_asset_maintenances"

