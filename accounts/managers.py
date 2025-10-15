from django.contrib.auth.models import BaseUserManager

class CustomUserManager(BaseUserManager):
    """
    Custom user model manager di mana email tidak wajib.
    """
    def create_user(self, username, password, **extra_fields):
        """
        Membuat dan menyimpan User dengan username dan password.
        Email tidak lagi wajib di sini.
        """
        if not username:
            raise ValueError('The Username must be set')
        
        # Hapus email jika ada, kita akan menanganinya di extra_fields
        extra_fields.pop('email', None)

        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password, **extra_fields):
        """
        Membuat dan menyimpan superuser.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(username, password, **extra_fields)
