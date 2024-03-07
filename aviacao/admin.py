from django.contrib import admin

# Register your models here.
from .models import *


@admin.register(TecnicoAgricola)
class TecnicoAgricolaAdmin(admin.ModelAdmin):
    list_display = ("nome", "crea_number")
