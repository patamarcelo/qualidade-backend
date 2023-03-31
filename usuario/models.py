from django.db import models
import datetime
import uuid

from django.utils.html import mark_safe

# from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.files.storage import FileSystemStorage
from django.db.models import FileField

import os


def get_file_path(instance, filename):
    ext = filename.split(".")[-1]
    name = filename.split(".")[0]
    date_file = datetime.datetime.now().strftime("%Y%m%d")
    user_name = instance.first_name.lower() if instance.first_name else ""
    filename = f"users/{user_name}_{date_file}_{name}_{str(uuid.uuid4())[:8]}.{ext}"
    return filename


class UsuarioManager(BaseUserManager):

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("O e-mail é Obrigatório")
        email = self.normalize_email(email)
        user = self.model(email=email, username=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        # extra_fields.setdefault('is_staff', True) padrao como False
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("image", None)

        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser precisa ter is_superuser=True")

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser precisa ter is_staff=True")

        return self._create_user(email, password, **extra_fields)


class CustomUsuario(AbstractUser):
    email = models.EmailField("E-mail", unique=True)
    fone = models.CharField("Telefone", max_length=15)
    first_name = models.CharField("First Name", max_length=15)
    last_name = models.CharField("Last Name", max_length=15)
    last_name = models.CharField("Last Name", max_length=15)
    is_staff = models.BooleanField("Membro da equipe", default=False)
    # image      = models.ImageField(storage=DropBoxStorage(), default='images/User1.jpg', blank=True)
    # image      = models.ImageField(upload_to=get_file_path, default='images/User1.jpg', blank=True)

    api_key = models.CharField("Api Key", max_length=200, blank=True, null=True)
    api_secret = models.CharField("Api Secret", max_length=200, blank=True, null=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name", "fone"]

    def image_tag(self):
        from django.utils.html import escape

        # return u'<img src="%s" />' % escape(self.image)
        return mark_safe(
            '<img src="%s" width="50" height="50" border-radius="10" />'
            % (self.image.url)
        )

    image_tag.short_description = "Foto"
    image_tag.allow_tags = True

    def __str__(self):
        return self.email

    objects = UsuarioManager()
