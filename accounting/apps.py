from django.apps import AppConfig


class AccountingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounting'
    
    def ready(self):
        # Import signal handlers for automatic journal entry creation
        import accounting.integration
