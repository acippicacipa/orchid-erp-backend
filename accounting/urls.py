from rest_framework.routers import DefaultRouter
from .views import (
    AccountTypeViewSet, AccountViewSet, JournalEntryViewSet, 
    FiscalYearViewSet, AccountingPeriodViewSet, TaxRateViewSet,
    BankAccountViewSet, FinancialReportsViewSet,
    LegacyJournalEntryViewSet, JournalItemViewSet, LedgerViewSet
)

router = DefaultRouter()
router.register(r'account-types', AccountTypeViewSet)
router.register(r'accounts', AccountViewSet)
router.register(r'journal-entries', JournalEntryViewSet)
router.register(r'fiscal-years', FiscalYearViewSet)
router.register(r'accounting-periods', AccountingPeriodViewSet)
router.register(r'tax-rates', TaxRateViewSet)
router.register(r'bank-accounts', BankAccountViewSet)
router.register(r'financial-reports', FinancialReportsViewSet, basename='financial-reports')

# Legacy endpoints for backward compatibility
router.register(r'legacy-journal-entries', LegacyJournalEntryViewSet, basename='legacy-journal-entry')
router.register(r'journal-items', JournalItemViewSet, basename='journal-item')
router.register(r'ledgers', LedgerViewSet, basename='ledger')

urlpatterns = router.urls


