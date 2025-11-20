from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone
from datetime import datetime, date
from decimal import Decimal

from .models import (
    AccountType, Account, JournalEntry, JournalEntryLine,
    FiscalYear, AccountingPeriod, TaxRate, BankAccount,
    JournalItem, Ledger
)
from .serializers import (
    AccountTypeSerializer, AccountSerializer, JournalEntrySerializer,
    CreateJournalEntrySerializer, JournalEntryLineSerializer,
    FiscalYearSerializer, AccountingPeriodSerializer, TaxRateSerializer,
    BankAccountSerializer, TrialBalanceSerializer, GeneralLedgerSerializer,
    IncomeStatementSerializer, BalanceSheetSerializer, JournalItemSerializer,
    LedgerSerializer, LegacyJournalEntrySerializer
)

class AccountTypeViewSet(viewsets.ModelViewSet):
    queryset = AccountType.objects.all()
    serializer_class = AccountTypeSerializer
    permission_classes = [IsAuthenticated]

class AccountViewSet(viewsets.ModelViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = Account.objects.select_related('account_type', 'parent_account')
        
        # Filter by account type
        account_type = self.request.query_params.get('account_type')
        if account_type:
            queryset = queryset.filter(account_type__category=account_type)
        
        # Filter by active status
        is_active_param = self.request.query_params.get('is_active')
        if is_active_param is not None:
            is_active_bool = is_active_param.lower() == 'true'
            queryset = queryset.filter(is_active=is_active_bool)
            
            # Jika pengguna secara spesifik meminta akun yang AKTIF,
            # tambahkan juga filter untuk allow_manual_entries.
            if is_active_bool:
                queryset = queryset.filter(allow_manual_entries=True)
        
        # Search by name or code
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(code__icontains=search)
            )
        
        return queryset.order_by('code')
    
    @action(detail=True, methods=['get'])
    def balance(self, request, pk=None):
        """Get account balance as of specific date"""
        account = self.get_object()
        as_of_date = request.query_params.get('as_of_date')
        
        if as_of_date:
            try:
                as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'error': 'Invalid date format. Use YYYY-MM-DD'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        balance = account.get_balance(as_of_date)
        return Response({
            'account': AccountSerializer(account).data,
            'balance': balance,
            'balance_formatted': f"Rp {balance:,.2f}",
            'as_of_date': as_of_date or timezone.now().date()
        })
    
    @action(detail=False, methods=['get'])
    def chart_of_accounts(self, request):
        """Get hierarchical chart of accounts"""
        accounts = Account.objects.filter(is_active=True).select_related('account_type', 'parent_account')
        
        # Group by account type
        chart = {}
        for account in accounts:
            category = account.account_type.category
            if category not in chart:
                chart[category] = {
                    'category': category,
                    'accounts': []
                }
            chart[category]['accounts'].append(AccountSerializer(account).data)
        
        return Response(chart)

class JournalEntryViewSet(viewsets.ModelViewSet):
    queryset = JournalEntry.objects.all()
    serializer_class = JournalEntrySerializer
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CreateJournalEntrySerializer
        return JournalEntrySerializer
    
    def get_queryset(self):
        queryset = JournalEntry.objects.select_related('created_by', 'posted_by').prefetch_related('lines__account')
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by entry type
        entry_type = self.request.query_params.get('entry_type')
        if entry_type:
            queryset = queryset.filter(entry_type=entry_type)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(entry_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(entry_date__lte=end_date)
        
        return queryset.order_by('-entry_date', '-created_at')
    
    @action(detail=True, methods=['post'])
    def post_entry(self, request, pk=None):
        """Post a journal entry"""
        journal_entry = self.get_object()
        
        try:
            journal_entry.post_entry(request.user)
            return Response({
                'message': 'Journal entry posted successfully',
                'entry': JournalEntrySerializer(journal_entry).data
            })
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def cancel_entry(self, request, pk=None):
        """Cancel a journal entry"""
        journal_entry = self.get_object()
        
        if journal_entry.status != 'DRAFT':
            return Response(
                {'error': 'Only draft entries can be cancelled'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        journal_entry.status = 'CANCELLED'
        journal_entry.save()
        
        return Response({
            'message': 'Journal entry cancelled successfully',
            'entry': JournalEntrySerializer(journal_entry).data
        })

class FiscalYearViewSet(viewsets.ModelViewSet):
    queryset = FiscalYear.objects.all()
    serializer_class = FiscalYearSerializer
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get current fiscal year"""
        current_fy = FiscalYear.objects.filter(is_current=True).first()
        if current_fy:
            return Response(FiscalYearSerializer(current_fy).data)
        return Response({'error': 'No current fiscal year set'}, status=status.HTTP_404_NOT_FOUND)

class AccountingPeriodViewSet(viewsets.ModelViewSet):
    queryset = AccountingPeriod.objects.all()
    serializer_class = AccountingPeriodSerializer
    permission_classes = [IsAuthenticated]

class TaxRateViewSet(viewsets.ModelViewSet):
    queryset = TaxRate.objects.all()
    serializer_class = TaxRateSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = TaxRate.objects.select_related('account')
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        # Filter by tax type
        tax_type = self.request.query_params.get('tax_type')
        if tax_type:
            queryset = queryset.filter(tax_type=tax_type)
        
        return queryset.order_by('tax_type', 'name')

class BankAccountViewSet(viewsets.ModelViewSet):
    queryset = BankAccount.objects.all()
    serializer_class = BankAccountSerializer
    permission_classes = [IsAuthenticated]

# Financial Reports Views
class FinancialReportsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def trial_balance(self, request):
        """Generate trial balance report"""
        as_of_date = request.query_params.get('as_of_date')
        if as_of_date:
            try:
                as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'error': 'Invalid date format. Use YYYY-MM-DD'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            as_of_date = timezone.now().date()
        
        accounts = Account.objects.filter(is_active=True, is_header_account=False).select_related('account_type')
        trial_balance_data = []
        total_debits = Decimal('0.00')
        total_credits = Decimal('0.00')
        
        for account in accounts:
            balance = account.get_balance(as_of_date)
            
            if account.account_type.category in ['ASSET', 'EXPENSE']:
                debit_balance = balance if balance > 0 else Decimal('0.00')
                credit_balance = abs(balance) if balance < 0 else Decimal('0.00')
            else:  # LIABILITY, EQUITY, REVENUE
                credit_balance = balance if balance > 0 else Decimal('0.00')
                debit_balance = abs(balance) if balance < 0 else Decimal('0.00')
            
            if debit_balance != 0 or credit_balance != 0:
                trial_balance_data.append({
                    'account_code': account.code,
                    'account_name': account.name,
                    'account_type': account.account_type.category,
                    'debit_balance': debit_balance,
                    'credit_balance': credit_balance,
                })
                
                total_debits += debit_balance
                total_credits += credit_balance
        
        serializer = TrialBalanceSerializer(trial_balance_data, many=True)
        
        return Response({
            'as_of_date': as_of_date,
            'accounts': serializer.data,
            'total_debits': total_debits,
            'total_credits': total_credits,
            'total_debits_formatted': f"Rp {total_debits:,.2f}",
            'total_credits_formatted': f"Rp {total_credits:,.2f}",
            'is_balanced': abs(total_debits - total_credits) < 0.01
        })
    
    @action(detail=False, methods=['get'])
    def general_ledger(self, request):
        """Generate general ledger report"""
        account_id = request.query_params.get('account_id')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if not account_id:
            return Response(
                {'error': 'account_id parameter is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            account = Account.objects.get(id=account_id)
        except Account.DoesNotExist:
            return Response(
                {'error': 'Account not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Parse dates
        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Get journal entry lines for this account
        entries_query = JournalEntryLine.objects.filter(
            account=account,
            journal_entry__status='POSTED'
        ).select_related('journal_entry')
        
        if start_date:
            entries_query = entries_query.filter(journal_entry__entry_date__gte=start_date)
        if end_date:
            entries_query = entries_query.filter(journal_entry__entry_date__lte=end_date)
        
        entries = entries_query.order_by('journal_entry__entry_date', 'journal_entry__created_at')
        
        # Calculate running balance
        opening_balance = account.opening_balance
        if start_date:
            # Calculate opening balance as of start date
            prior_entries = JournalEntryLine.objects.filter(
                account=account,
                journal_entry__status='POSTED',
                journal_entry__entry_date__lt=start_date
            )
            
            prior_debits = sum(entry.debit_amount for entry in prior_entries)
            prior_credits = sum(entry.credit_amount for entry in prior_entries)
            
            if account.account_type.category in ['ASSET', 'EXPENSE']:
                opening_balance = account.opening_balance + prior_debits - prior_credits
            else:
                opening_balance = account.opening_balance + prior_credits - prior_debits
        
        # Build entries with running balance
        ledger_entries = []
        running_balance = opening_balance
        total_debits = Decimal('0.00')
        total_credits = Decimal('0.00')
        
        for entry in entries:
            if account.account_type.category in ['ASSET', 'EXPENSE']:
                running_balance += entry.debit_amount - entry.credit_amount
            else:
                running_balance += entry.credit_amount - entry.debit_amount
            
            total_debits += entry.debit_amount
            total_credits += entry.credit_amount
            
            ledger_entries.append({
                'date': entry.journal_entry.entry_date,
                'entry_number': entry.journal_entry.entry_number,
                'description': entry.description or entry.journal_entry.description,
                'reference': entry.journal_entry.reference_number,
                'debit': entry.debit_amount,
                'credit': entry.credit_amount,
                'balance': running_balance,
                'debit_formatted': f"Rp {entry.debit_amount:,.2f}" if entry.debit_amount > 0 else "",
                'credit_formatted': f"Rp {entry.credit_amount:,.2f}" if entry.credit_amount > 0 else "",
                'balance_formatted': f"Rp {running_balance:,.2f}",
            })
        
        return Response({
            'account': AccountSerializer(account).data,
            'period_start': start_date,
            'period_end': end_date,
            'opening_balance': opening_balance,
            'closing_balance': running_balance,
            'total_debits': total_debits,
            'total_credits': total_credits,
            'entries': ledger_entries,
            'opening_balance_formatted': f"Rp {opening_balance:,.2f}",
            'closing_balance_formatted': f"Rp {running_balance:,.2f}",
            'total_debits_formatted': f"Rp {total_debits:,.2f}",
            'total_credits_formatted': f"Rp {total_credits:,.2f}",
        })
    
    @action(detail=False, methods=['get'])
    def income_statement(self, request):
        """Generate income statement (profit & loss)"""
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if not start_date or not end_date:
            return Response(
                {'error': 'start_date and end_date parameters are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get revenue and expense accounts
        revenue_accounts = Account.objects.filter(
            account_type__category='REVENUE',
            is_active=True,
            is_header_account=False
        ).select_related('account_type')
        
        expense_accounts = Account.objects.filter(
            account_type__category='EXPENSE',
            is_active=True,
            is_header_account=False
        ).select_related('account_type')
        
        # Calculate revenue
        revenue_data = []
        total_revenue = Decimal('0.00')
        
        for account in revenue_accounts:
            # Get entries for the period
            entries = JournalEntryLine.objects.filter(
                account=account,
                journal_entry__status='POSTED',
                journal_entry__entry_date__gte=start_date,
                journal_entry__entry_date__lte=end_date
            )
            
            period_credits = sum(entry.credit_amount for entry in entries)
            period_debits = sum(entry.debit_amount for entry in entries)
            net_revenue = period_credits - period_debits
            
            if net_revenue != 0:
                revenue_data.append({
                    'account_code': account.code,
                    'account_name': account.name,
                    'amount': net_revenue,
                    'amount_formatted': f"Rp {net_revenue:,.2f}"
                })
                total_revenue += net_revenue
        
        # Calculate expenses
        expense_data = []
        total_expenses = Decimal('0.00')
        
        for account in expense_accounts:
            # Get entries for the period
            entries = JournalEntryLine.objects.filter(
                account=account,
                journal_entry__status='POSTED',
                journal_entry__entry_date__gte=start_date,
                journal_entry__entry_date__lte=end_date
            )
            
            period_debits = sum(entry.debit_amount for entry in entries)
            period_credits = sum(entry.credit_amount for entry in entries)
            net_expense = period_debits - period_credits
            
            if net_expense != 0:
                expense_data.append({
                    'account_code': account.code,
                    'account_name': account.name,
                    'amount': net_expense,
                    'amount_formatted': f"Rp {net_expense:,.2f}"
                })
                total_expenses += net_expense
        
        net_income = total_revenue - total_expenses
        
        return Response({
            'period_start': start_date,
            'period_end': end_date,
            'revenue_accounts': revenue_data,
            'expense_accounts': expense_data,
            'total_revenue': total_revenue,
            'total_expenses': total_expenses,
            'net_income': net_income,
            'total_revenue_formatted': f"Rp {total_revenue:,.2f}",
            'total_expenses_formatted': f"Rp {total_expenses:,.2f}",
            'net_income_formatted': f"Rp {net_income:,.2f}",
        })
    
    @action(detail=False, methods=['get'])
    def balance_sheet(self, request):
        """Generate balance sheet"""
        as_of_date = request.query_params.get('as_of_date')
        if as_of_date:
            try:
                as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'error': 'Invalid date format. Use YYYY-MM-DD'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            as_of_date = timezone.now().date()
        
        # Get accounts by category
        asset_accounts = Account.objects.filter(
            account_type__category='ASSET',
            is_active=True,
            is_header_account=False
        ).select_related('account_type')
        
        liability_accounts = Account.objects.filter(
            account_type__category='LIABILITY',
            is_active=True,
            is_header_account=False
        ).select_related('account_type')
        
        equity_accounts = Account.objects.filter(
            account_type__category='EQUITY',
            is_active=True,
            is_header_account=False
        ).select_related('account_type')
        
        # Calculate assets
        assets_data = []
        total_assets = Decimal('0.00')
        
        for account in asset_accounts:
            balance = account.get_balance(as_of_date)
            if balance != 0:
                assets_data.append({
                    'account_code': account.code,
                    'account_name': account.name,
                    'amount': balance,
                    'amount_formatted': f"Rp {balance:,.2f}"
                })
                total_assets += balance
        
        # Calculate liabilities
        liabilities_data = []
        total_liabilities = Decimal('0.00')
        
        for account in liability_accounts:
            balance = account.get_balance(as_of_date)
            if balance != 0:
                liabilities_data.append({
                    'account_code': account.code,
                    'account_name': account.name,
                    'amount': balance,
                    'amount_formatted': f"Rp {balance:,.2f}"
                })
                total_liabilities += balance
        
        # Calculate equity
        equity_data = []
        total_equity = Decimal('0.00')
        
        for account in equity_accounts:
            balance = account.get_balance(as_of_date)
            if balance != 0:
                equity_data.append({
                    'account_code': account.code,
                    'account_name': account.name,
                    'amount': balance,
                    'amount_formatted': f"Rp {balance:,.2f}"
                })
                total_equity += balance
        
        return Response({
            'as_of_date': as_of_date,
            'assets': assets_data,
            'liabilities': liabilities_data,
            'equity': equity_data,
            'total_assets': total_assets,
            'total_liabilities': total_liabilities,
            'total_equity': total_equity,
            'total_assets_formatted': f"Rp {total_assets:,.2f}",
            'total_liabilities_formatted': f"Rp {total_liabilities:,.2f}",
            'total_equity_formatted': f"Rp {total_equity:,.2f}",
            'total_liabilities_equity': total_liabilities + total_equity,
            'total_liabilities_equity_formatted': f"Rp {(total_liabilities + total_equity):,.2f}",
            'is_balanced': abs(total_assets - (total_liabilities + total_equity)) < 0.01
        })

# Legacy views for backward compatibility
class LegacyJournalEntryViewSet(viewsets.ModelViewSet):
    queryset = JournalEntry.objects.all()
    serializer_class = LegacyJournalEntrySerializer
    permission_classes = [IsAuthenticated]

class JournalItemViewSet(viewsets.ModelViewSet):
    queryset = JournalItem.objects.all()
    serializer_class = JournalItemSerializer
    permission_classes = [IsAuthenticated]

class LedgerViewSet(viewsets.ModelViewSet):
    queryset = Ledger.objects.all()
    serializer_class = LedgerSerializer
    permission_classes = [IsAuthenticated]


