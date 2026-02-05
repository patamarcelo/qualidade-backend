# usuario/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import CustomUsuarioCreationForm, CustomUsuarioChangeForm
from .models import CustomUsuario
    
    
    
@admin.register(CustomUsuario)
class CustomUsuarioAdmin(UserAdmin):
    add_form = CustomUsuarioCreationForm
    form = CustomUsuarioChangeForm
    model = CustomUsuario

    list_display = ("first_name", "last_name", "email", "origin_app", "fone", "is_staff", "is_active")

    list_filter = ("origin_app", "is_staff", "is_active", "is_superuser", "groups")

    search_fields = ("email", "first_name", "last_name", "fone")
    ordering = ("email",)

    readonly_fields = ("image_tag", "last_login", "date_joined")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Origem", {"fields": ("origin_app",)}),
        ("Informações pessoais", {"fields": ("first_name", "last_name", "fone")}),
        ("Permissões", {"fields": ("is_active", "is_superuser", "is_staff", "groups", "user_permissions")}),
        ("Datas Importantes", {"fields": ("last_login", "date_joined")}),
        ("Binance API", {"fields": ("api_secret", "api_key")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "origin_app", "first_name", "last_name", "fone", "password1", "password2", "is_staff", "is_superuser", "is_active"),
        }),
    )