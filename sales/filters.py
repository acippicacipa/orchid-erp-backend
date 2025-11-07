import django_filters
from .models import SalesOrder

class SalesOrderFilter(django_filters.FilterSet):
    """
    FilterSet kustom untuk SalesOrder.
    """
    
    # --- INI BAGIAN PENTINGNYA ---
    # Kita mendefinisikan ulang filter untuk field 'status'.
    status = django_filters.CharFilter(method='filter_by_multiple_statuses')
    has_invoice = django_filters.BooleanFilter(method='filter_by_invoice_status')

    class Meta:
        model = SalesOrder
        # Daftarkan field lain yang ingin Anda filter seperti biasa
        fields = ['status', 'customer', 'order_date', 'has_invoice']

    def filter_by_multiple_statuses(self, queryset, name, value):
        """
        Metode kustom untuk memfilter berdasarkan satu atau beberapa status.
        Nilai status bisa dipisahkan dengan koma.
        Contoh: /?status=CONFIRMED,PROCESSING
        """
        # Pisahkan nilai 'value' berdasarkan koma
        statuses = value.split(',')
        
        # Lakukan query 'in' pada queryset
        return queryset.filter(status__in=statuses)

    def filter_by_invoice_status(self, queryset, name, value):
        """
        Filter SO berdasarkan apakah mereka sudah memiliki invoice terkait atau belum.
        - /?has_invoice=true -> akan mengembalikan SO yang SUDAH punya invoice.
        - /?has_invoice=false -> akan mengembalikan SO yang BELUM punya invoice.
        """
        # `value` akan menjadi True atau False.
        # Kita menggunakan lookup `invoices_m2m__isnull` pada relasi ManyToMany.
        # `isnull=True` berarti tidak ada invoice yang terhubung.
        # `isnull=False` berarti ada setidaknya satu invoice yang terhubung.
        if value is True:
            return queryset.filter(invoices_m2m__isnull=False).distinct()
        elif value is False:
            return queryset.filter(invoices_m2m__isnull=True).distinct()
        
        # Jika parameter tidak diberikan, jangan filter apa-apa
        return queryset
