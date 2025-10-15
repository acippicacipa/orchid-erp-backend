from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import UserProfile

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile_on_user_creation(sender, instance, created, **kwargs):
    """
    Secara otomatis membuat UserProfile HANYA saat User baru dibuat.
    """
    # 'created' adalah boolean yang bernilai True jika ini adalah
    # pertama kalinya objek disimpan ke database.
    if created:
        # Buat UserProfile untuk instance User yang baru dibuat.
        # Method save() dari UserProfile akan otomatis dipanggil,
        # yang juga akan men-generate employee_id.
        UserProfile.objects.create(user=instance)