from django.core.management.base import BaseCommand
from accounting.models import Account

class Command(BaseCommand):
    help = "Sets up initial chart of accounts for the ERP system."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Setting up initial chart of accounts..."))

        accounts_data = [
            # Assets
            {"name": "Cash", "account_type": "ASSET", "account_number": "1000"},
            {"name": "Bank", "account_type": "ASSET", "account_number": "1010"},
            {"name": "Accounts Receivable", "account_type": "ASSET", "account_number": "1200"},
            {"name": "Inventory", "account_type": "ASSET", "account_number": "1400"},
            {"name": "Prepaid Expenses", "account_type": "ASSET", "account_number": "1500"},
            {"name": "Fixed Assets", "account_type": "ASSET", "account_number": "1800"},

            # Liabilities
            {"name": "Accounts Payable", "account_type": "LIABILITY", "account_number": "2000"},
            {"name": "Salaries Payable", "account_type": "LIABILITY", "account_number": "2100"},
            {"name": "Taxes Payable", "account_type": "LIABILITY", "account_number": "2200"},
            {"name": "Loans Payable", "account_type": "LIABILITY", "account_number": "2500"},

            # Equity
            {"name": "Owner's Equity", "account_type": "EQUITY", "account_number": "3000"},
            {"name": "Retained Earnings", "account_type": "EQUITY", "account_number": "3200"},

            # Revenue
            {"name": "Sales Revenue", "account_type": "REVENUE", "account_number": "4000"},
            {"name": "Service Revenue", "account_type": "REVENUE", "account_number": "4100"},

            # Expenses
            {"name": "Cost of Goods Sold", "account_type": "EXPENSE", "account_number": "5000"},
            {"name": "Salaries Expense", "account_type": "EXPENSE", "account_number": "6000"},
            {"name": "Rent Expense", "account_type": "EXPENSE", "account_number": "6100"},
            {"name": "Utilities Expense", "account_type": "EXPENSE", "account_number": "6200"},
            {"name": "Marketing Expense", "account_type": "EXPENSE", "account_number": "6300"},
            {"name": "Depreciation Expense", "account_type": "EXPENSE", "account_number": "6400"},
        ]

        for data in accounts_data:
            account, created = Account.objects.get_or_create(
                account_number=data["account_number"],
                defaults={
                    "name": data["name"],
                    "account_type": data["account_type"],
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Successfully created account: {account.name}"))
            else:
                self.stdout.write(self.style.WARNING(f"Account already exists: {account.name}"))

        self.stdout.write(self.style.SUCCESS("Initial chart of accounts setup complete."))


