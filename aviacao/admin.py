from django.contrib import admin

# Register your models here.
from .models import *

from django_json_widget.widgets import JSONEditorWidget
import locale

locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')


class AplicacaoAviaoInline(admin.StackedInline):
    model = AplicacaoAviao
    extra = 0
    autocomplete_fields = ["defensivo"]
    fieldsets = [
        (
            "Produto / Dose",
            {
                "fields": (
                    (
                        "defensivo",
                        "dose",
                    ),
                )
            },
        )
    ]


class CondicoesMeteorologicasInline(admin.StackedInline):
    model = CondicoesMeteorologicas
    extra = 0
    fieldsets = [
        (
            "Dados",
            {
                "fields": (
                    (
                        "temperatura_inicial",
                        "temperatura_final",
                    ),
                    (
                        "umidade_relativa_incial",
                        "umidade_relativa_final",
                    ),
                    (
                        "velocidade_vento_inicial",
                        "velocidade_vento_final",
                    ),
                )
            },
        )
    ]


class ParametrosAplicacaoInline(admin.StackedInline):
    model = ParametrosAplicacao
    extra = 0
    fieldsets = [
        (
            "Parâmetros",
            {
                "fields": (
                    ("temperatura_max",),
                    (
                        "umidade_relativa_min",
                        "umidade_relativa_ax",
                    ),
                    ("equipamento"),
                    (
                        "altura_do_voo",
                        "largura_da_faixa",
                    ),
                    ("receituario_agronomo_n",),
                    ("data_emissao",),
                )
            },
        )
    ]


@admin.register(TecnicoAgricola)
class TecnicoAgricolaAdmin(admin.ModelAdmin):
    list_display = ("nome", "crea_number")


@admin.register(Aeronave)
class AeronaveAdmin(admin.ModelAdmin):
    list_display = ("prefixo",)


@admin.register(Pista)
class PistaAdmin(admin.ModelAdmin):
    list_display = ("projeto", "nome", "coordenadas")
    search_fields = ["projeto"]

    formfield_overrides = {
        models.JSONField: {
            "widget": JSONEditorWidget(width="200%", height="50vh", mode="tree")
        },
    }


@admin.register(Piloto)
class PilotoAdmin(admin.ModelAdmin):
    list_display = ("nome", "anac")


@admin.register(Gerente)
class GerenteAdmin(admin.ModelAdmin):
    # criar get projetos list display
    list_display = ["nome"]
    search_fields = ["nome"]


@admin.register(ParametrosAplicacao)
class ParametrosAplicacaoAdmin(admin.ModelAdmin):
    list_display = ["os"]
    fieldsets = [
        (
            "Dados",
            {
                "fields": (
                    ("os",),
                    ("temperatura_max",),
                    (
                        "umidade_relativa_min",
                        "umidade_relativa_ax",
                    ),
                    (
                        "altura_do_voo",
                        "largura_da_faixa",
                    ),
                    ("parcelas",),
                    ("receituario_agronomo_n",),
                    ("data_emissao",),
                )
            },
        )
    ]


@admin.register(Ajudante)
class AjudanteAdmin(admin.ModelAdmin):
    list_display = ["nome"]

@admin.register(OrdemDeServico)
class OrdemDeServicoAdmin(admin.ModelAdmin):
    list_display = ("numero", "data")
    filter_horizontal = ("ajudante",)
    readonly_fields = ["criados", "get_tempo_aplicacao"]
    autocomplete_fields = ["encarregado_autoriza", "projeto", "parcelas", "tarifa_piloto", 'pista']
    inlines = [
        AplicacaoAviaoInline,
        CondicoesMeteorologicasInline,
        ParametrosAplicacaoInline,
    ]
    fieldsets = [
        (
            "Dados",
            {
                "fields": (
                    ("ativo", "criados"),
                    ("numero", "data"),
                    ("projeto", "parcelas"),
                    ("os_file"),
                    (
                        "data_inicial",
                        "data_final",
                    ),
                    ("cultura", "tipo_servico"),
                    ("area", "volume"),
                    ("horimetro_inicial", "horimetro_final"),
                    ("get_tempo_aplicacao"),
                    ("combustivel", "oleo_lubrificante"),
                    ("ajudante"),
                    ("encarregado_autoriza"),
                ),
            },
        ),
        (
            "Aeronave",
            {"fields": (("aeronave", "piloto"),("pista", "tarifa_piloto"), ("uso_gps",))},
        ),
        (
            "Responsável",
            {"fields": (("tecnico_agricola_executor"),)},
        ),
        (
            "Observações",
            {"fields": (("observacao",),)},
        ),
        # (
        #     "Produtos",
        #     {"fields": (("os_related_aplicacao",),)},
        # ),
    ]


@admin.register(CondicoesMeteorologicas)
class CondicoesMeteorologicasAdmin(admin.ModelAdmin):
    list_display = ("os", "temperatura_inicial", "temperatura_final")


@admin.register(TempoAplicacao)
class TempoAplicacaoAdmin(admin.ModelAdmin):
    list_display = ("os", "inicio_aplicacao", "final_aplicacao")


@admin.register(AplicacaoAviao)
class AplicacaoAviaoAdmin(admin.ModelAdmin):
    list_display = ("os", "defensivo", "dose", "ativo")


@admin.register(TabelaPilotos)
class TabelaPilotosAdmin(admin.ModelAdmin):
    list_display = ("tipo", "safra_description", "vazao", "get_price_descriptio", "ativo")
    list_filter = ["tipo"]
    search_fields = ["tipo"]
    fieldsets = [
        (
            "Dados",
            {
                "fields": (
                    ("ativo"),
                    ("tipo"),
                    ("safra", "ciclo"),
                    ("vazao", "preco"),
                    ("observacao"),
                )
            },
        )
    ]
    
    
    def safra_description(self, obj):
        return f"{obj.safra.safra} - {obj.ciclo.ciclo}"
    safra_description.short_description = "Safra/Ciclo"
    
    def get_price_descriptio(self, obj):
        return f'R$ {locale.currency(obj.preco, grouping=True, symbol=False)}'
    get_price_descriptio.short_description = "Preço"
    
    