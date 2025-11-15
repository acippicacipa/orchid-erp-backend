from django.apps import AppConfig


class InventoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'inventory'

    def ready(self):
        """
        Metode ini akan dipanggil saat aplikasi 'inventory' siap.
        Kita mengimpor signals di sini.
        """
        import inventory.signals  # Ini akan mendaftarkan receiver kita