from django.contrib import admin

from django.contrib.auth.admin import UserAdmin

from .forms import CustomUsuarioCreationForm, CustomUsuarioChangeForm
from .models import CustomUsuario


@admin.register(CustomUsuario)
class CustomUsuarioAdmin(UserAdmin):
    add_form = CustomUsuarioCreationForm
    form = CustomUsuarioChangeForm
    model = CustomUsuario
    list_display = (
        "first_name",
        "last_name",
        "email",
        "fone",
        "is_staff",
        "is_active",
        # "image_tag",
    )
    readonly_fields = ("image_tag",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Informações pessoais", {"fields": ("first_name", "last_name", "fone")}),
        (
            "Permissões",
            {
                "fields": (
                    "is_active",
                    "is_superuser",
                    "is_staff",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Datas Importantes", {"fields": ("last_login", "date_joined")}),
        # ('Outros', { 'fields': ('image',)}),
        ("Binance API", {"fields": ("api_secret", "api_key")}),
    )
