from rest_framework import serializers
from inventory.serializers import LocationSerializer
from .models import (
    AccountType, Account, JournalEntry, JournalEntryLine, 
    FiscalYear, AccountingPeriod, TaxRate, BankAccount,
    JournalItem, Ledger, Asset, AssetCategory, AssetDepreciation, AssetMaintenance
)

class AccountTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountType
        fields = '__all__'

class AccountSerializer(serializers.ModelSerializer):
    account_type_name = serializers.CharField(source='account_type.name', read_only=True)
    account_category = serializers.CharField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    current_balance_formatted = serializers.SerializerMethodField()
    parent_account_name = serializers.CharField(source='parent_account.name', read_only=True)
    
    class Meta:
        model = Account
        fields = [
            'id', 'account_type', 'account_type_name', 'code', 'name', 'description',
            'parent_account', 'parent_account_name', 'is_active', 'is_header_account',
            'allow_manual_entries', 'opening_balance', 'current_balance', 
            'current_balance_formatted', 'tax_account', 'bank_account', 'cash_account',
            'notes', 'account_category', 'full_name', 'created_at', 'updated_at'
        ]
    
    def get_current_balance_formatted(self, obj):
        return f"Rp {obj.current_balance:,.2f}"

class JournalEntryLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source='account.code', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    debit_formatted = serializers.SerializerMethodField()
    credit_formatted = serializers.SerializerMethodField()
    
    class Meta:
        model = JournalEntryLine
        fields = [
            'id', 'account', 'account_code', 'account_name', 'description',
            'debit_amount', 'credit_amount', 'debit_formatted', 'credit_formatted',
            'reference_id', 'reference_type', 'created_at', 'updated_at'
        ]
    
    def get_debit_formatted(self, obj):
        return f"Rp {obj.debit_amount:,.2f}" if obj.debit_amount > 0 else ""
    
    def get_credit_formatted(self, obj):
        return f"Rp {obj.credit_amount:,.2f}" if obj.credit_amount > 0 else ""

class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalEntryLineSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    posted_by_name = serializers.CharField(source='posted_by.username', read_only=True)
    total_debit_formatted = serializers.SerializerMethodField()
    total_credit_formatted = serializers.SerializerMethodField()
    is_balanced = serializers.SerializerMethodField()
    
    class Meta:
        model = JournalEntry
        fields = [
            'id', 'entry_number', 'entry_date', 'entry_type', 'reference_number',
            'description', 'status', 'posted_date', 'posted_by', 'posted_by_name',
            'total_debit', 'total_credit', 'total_debit_formatted', 'total_credit_formatted',
            'is_balanced', 'sales_order', 'purchase_order', 'goods_receipt',
            'notes', 'created_by', 'created_by_name', 'lines', 'created_at', 'updated_at'
        ]
    
    def get_total_debit_formatted(self, obj):
        return f"Rp {obj.total_debit:,.2f}"
    
    def get_total_credit_formatted(self, obj):
        return f"Rp {obj.total_credit:,.2f}"
    
    def get_is_balanced(self, obj):
        return abs(obj.total_debit - obj.total_credit) < 0.01

class CreateJournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalEntryLineSerializer(many=True)
    
    class Meta:
        model = JournalEntry
        fields = [
            'entry_date', 'entry_type', 'reference_number', 'description',
            'notes', 'lines'
        ]
    
    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        validated_data['created_by'] = self.context['request'].user
        
        journal_entry = JournalEntry.objects.create(**validated_data)
        
        total_debit = 0
        total_credit = 0
        
        for line_data in lines_data:
            line = JournalEntryLine.objects.create(
                journal_entry=journal_entry,
                **line_data
            )
            total_debit += line.debit_amount
            total_credit += line.credit_amount
        
        journal_entry.total_debit = total_debit
        journal_entry.total_credit = total_credit
        journal_entry.save()
        
        return journal_entry

class FiscalYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiscalYear
        fields = '__all__'

class AccountingPeriodSerializer(serializers.ModelSerializer):
    fiscal_year_name = serializers.CharField(source='fiscal_year.name', read_only=True)
    
    class Meta:
        model = AccountingPeriod
        fields = [
            'id', 'fiscal_year', 'fiscal_year_name', 'name', 'start_date', 
            'end_date', 'is_closed', 'closed_date', 'closed_by', 
            'created_at', 'updated_at'
        ]

class TaxRateSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    account_code = serializers.CharField(source='account.code', read_only=True)
    
    class Meta:
        model = TaxRate
        fields = [
            'id', 'name', 'tax_type', 'rate', 'account', 'account_name', 
            'account_code', 'is_active', 'effective_date', 'expiry_date',
            'description', 'created_at', 'updated_at'
        ]

class BankAccountSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    account_code = serializers.CharField(source='account.code', read_only=True)
    
    class Meta:
        model = BankAccount
        fields = [
            'id', 'account', 'account_name', 'account_code', 'bank_name',
            'account_number', 'account_holder', 'branch', 'swift_code',
            'iban', 'currency', 'is_active', 'created_at', 'updated_at'
        ]

# Legacy serializers for backward compatibility
class JournalItemSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    
    class Meta:
        model = JournalItem
        fields = '__all__'

class LegacyJournalEntrySerializer(serializers.ModelSerializer):
    items = JournalItemSerializer(many=True)

    class Meta:
        model = JournalEntry
        fields = '__all__'

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        journal_entry = JournalEntry.objects.create(**validated_data)
        for item_data in items_data:
            JournalItem.objects.create(journal_entry=journal_entry, **item_data)
        return journal_entry

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        
        instance = super().update(instance, validated_data)

        if items_data is not None:
            instance.items.all().delete() # Clear existing items
            for item_data in items_data:
                JournalItem.objects.create(journal_entry=instance, **item_data)
        
        return instance

class LedgerSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    journal_entry_reference = serializers.CharField(source='journal_item.journal_entry.reference_number', read_only=True)

    class Meta:
        model = Ledger
        fields = '__all__'

# Financial Reports Serializers
class TrialBalanceSerializer(serializers.Serializer):
    account_code = serializers.CharField()
    account_name = serializers.CharField()
    account_type = serializers.CharField()
    debit_balance = serializers.DecimalField(max_digits=15, decimal_places=2)
    credit_balance = serializers.DecimalField(max_digits=15, decimal_places=2)
    debit_formatted = serializers.SerializerMethodField()
    credit_formatted = serializers.SerializerMethodField()
    
    def get_debit_formatted(self, obj):
        return f"Rp {obj['debit_balance']:,.2f}" if obj['debit_balance'] > 0 else ""
    
    def get_credit_formatted(self, obj):
        return f"Rp {obj['credit_balance']:,.2f}" if obj['credit_balance'] > 0 else ""

class GeneralLedgerSerializer(serializers.Serializer):
    account = AccountSerializer()
    entries = serializers.ListField()
    opening_balance = serializers.DecimalField(max_digits=15, decimal_places=2)
    closing_balance = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_debits = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_credits = serializers.DecimalField(max_digits=15, decimal_places=2)

class IncomeStatementSerializer(serializers.Serializer):
    revenue_accounts = serializers.ListField()
    expense_accounts = serializers.ListField()
    total_revenue = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_expenses = serializers.DecimalField(max_digits=15, decimal_places=2)
    net_income = serializers.DecimalField(max_digits=15, decimal_places=2)
    period_start = serializers.DateField()
    period_end = serializers.DateField()

class BalanceSheetSerializer(serializers.Serializer):
    assets = serializers.ListField()
    liabilities = serializers.ListField()
    equity = serializers.ListField()
    total_assets = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_liabilities = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_equity = serializers.DecimalField(max_digits=15, decimal_places=2)
    as_of_date = serializers.DateField()

class AssetCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetCategory
        fields = '__all__'

class AssetMaintenanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetMaintenance
        fields = '__all__'

class AssetDepreciationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetDepreciation
        fields = '__all__'

class AssetSerializer(serializers.ModelSerializer):
    # Tampilkan nama, bukan hanya ID
    category_name = serializers.CharField(source='category.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    
    # Kalkulasi field secara on-the-fly
    book_value = serializers.SerializerMethodField()
    total_depreciation = serializers.SerializerMethodField()

    class Meta:
        model = Asset
        fields = [
            'id', 'asset_code', 'name', 'category', 'category_name', 'location', 
            'location_name', 'status', 'purchase_date', 'purchase_price', 
            'depreciation_method', 'useful_life_months', 'salvage_value',
            'disposal_date', 'disposal_price', 'book_value', 'total_depreciation',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['asset_code', 'book_value', 'total_depreciation']

    def get_total_depreciation(self, obj):
        # Menghitung total penyusutan yang sudah tercatat
        total = obj.depreciations.aggregate(total=models.Sum('amount'))['total']
        return total or 0

    def get_book_value(self, obj):
        # Nilai buku = Harga Perolehan - Total Akumulasi Penyusutan
        total_depreciation = self.get_total_depreciation(obj)
        return obj.purchase_price - total_depreciation


