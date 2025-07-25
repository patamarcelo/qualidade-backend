from django.db import models
from django.utils import timezone

from datetime import timedelta
import datetime

from django.db import connection
import json

from .utils import format_date_json
import decimal

connection.queries
from django.core.validators import RegexValidator, MinLengthValidator
from django.core.exceptions import ValidationError


from django.db.models import Count, Sum

import uuid
from os.path import join
import os

import dropbox
from django.conf import settings
from decimal import Decimal, ROUND_HALF_UP

# Create your models here.


class Base(models.Model):
    criados = models.DateTimeField("Criação", auto_now_add=True)
    modificado = models.DateTimeField("Atualização", auto_now=True)
    ativo = models.BooleanField("Ativo", default=True)
    observacao = models.TextField("Observação", blank=True, null=True)

    class Meta:
        abstract = True


# -------------  ------------- ESTRUTURA -------------  -------------#

class CotacaoDolar(models.Model):
    data  = models.DateTimeField(auto_now_add=True)
    valor = models.DecimalField(max_digits=10, decimal_places=4)

    class Meta:
        ordering = ["-data"]

    def __str__(self):
        return f"Cotação em {self.data.strftime('%Y-%m-%d %H:%M')} - R$ {self.valor}"

class Deposito(Base):
    nome = models.CharField("Nome", max_length=100, help_text="Depósito", unique=True)
    id_d = models.PositiveIntegerField("ID_D", unique=True)
    nome_fantasia = models.CharField(
        "Nome Fantasia",
        max_length=100,
        help_text="Depósito / Fantasia",
        unique=True,
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ["nome"]
        verbose_name = "Depósito"
        verbose_name_plural = "Depósitos"

    def __str__(self):
        return self.nome


class Fazenda(Base):
    nome = models.CharField("Nome", max_length=100, help_text="Fazenda", unique=True)
    id_d = models.PositiveIntegerField("ID_D", unique=True)
    id_responsavel_farmbox = models.IntegerField("ID Responsavel FarmBox",  blank=True, null=True)
    id_encarregado_farmbox = models.IntegerField("ID Encarregado FarmBox",  blank=True, null=True)

    capacidade_plantio_ha_dia = models.PositiveIntegerField(
        "Quantidade ha Plantio / dia",
        default=50,
        help_text="Capacidade Projetada Plantio ha/dia",
    )

    class Meta:
        ordering = ["nome"]
        verbose_name = "Fazenda"
        verbose_name_plural = "Fazendas"

    def __str__(self):
        return self.nome


class Projeto(Base):
    nome = models.CharField("Nome", max_length=100, help_text="Projeto", unique=True)
    id_d = models.IntegerField("ID_D", unique=True)
    id_farmbox = models.IntegerField("ID FarmBox", unique=True, blank=True, null=True)
    fazenda = models.ForeignKey(Fazenda, on_delete=models.PROTECT)
    quantidade_area_produtiva = models.DecimalField(
        "Area Produtiva",
        help_text="Informar Area Produtiva",
        blank=True,
        null=True,
        max_digits=10,
        decimal_places=2,
    )
    quantidade_area_carr = models.DecimalField(
        "Area Carr",
        help_text="",
        blank=True,
        null=True,
        max_digits=10,
        decimal_places=2,
    )
    quantidade_area_total = models.DecimalField(
        "Area Total",
        help_text="Quantidade Area Total",
        blank=True,
        null=True,
        max_digits=10,
        decimal_places=2,
    )

    capacidade_plantio_ha_dia = models.PositiveIntegerField(
        "Quantidade ha Plantio / dia",
        default=50,
        help_text="Capacidade Projetada Plantio ha/dia",
    )

    map_centro_id = models.JSONField(null=True, blank=True)
    map_zoom = models.DecimalField(
        "Zoom do Mapa",
        help_text="Zoom do Mapa",
        blank=True,
        null=True,
        max_digits=4,
        decimal_places=2,
    )

    class Meta:
        ordering = ["nome"]
        verbose_name = "Projeto"
        verbose_name_plural = "Projetos"

    def __str__(self):
        return f"{self.nome} / {self.fazenda}"


class Talhao(Base):
    id_talhao = models.CharField("ID Talhao", max_length=100, help_text="Talhao")
    id_unico = models.CharField(
        "ID_Unico", help_text="ID_Fazenda + Talhao", unique=True, max_length=10
    )
    fazenda = models.ForeignKey(Projeto, on_delete=models.PROTECT)
    area_total = models.DecimalField("Area Total", max_digits=6, decimal_places=2)
    modulo = models.CharField(
        "Módulo", max_length=20, help_text="Módulo do Talhão", blank=True, null=True
    )

    class Meta:
        order_with_respect_to = "fazenda"
        verbose_name = "Talhao"
        verbose_name_plural = "Talhoes"

    def __str__(self):
        nome_proj = (
            self.fazenda.nome.replace("Projeto", "")
            if "Projeto" in self.fazenda.nome
            else self.fazenda.nome
        )
        return f"{nome_proj} - {self.id_talhao}"


# -------------  ------------- PRODUTO -------------  -------------#

UNIDADE_CHOICES = (("l_ha", "LT"), ("kg_ha", "KG"), ("un_ha", "Hectare"))
FORMULACAO_CHOICES = (("liquido", "Líquido"), ("solido", "Sólido"), ('unidade','Unidade'))

TIPO_CHOICES = (
    ("acaricida", "Acaricida"),
    ("adjuvante", "Adjuvante"),
    ("biologico", "Biológico"),
    ("cobertura", "Cobertura"),
    ("fertilizante", "Fertilizante"),
    ("fungicida", "Fungicida"),
    ("herbicida", "Herbicida"),
    ("inseticida", "Inseticida"),
    ("lubrificante", "Lubrificante"),
    ("nutricao", "Nutrição"),
    ("oleo_mineral_vegetal", "Óleo Mineral/Vegetal"),
    ("operacao", 'Operação'),
    ("protetor", "Protetor"),
    ("regulador", "Regulador"),
    ("semente", "Semente"),
)


class Defensivo(Base):
    produto = models.CharField("Descrição Defensivo", max_length=140, unique=True)
    unidade_medida = models.CharField(
        "Unidade de Medida", max_length=20, choices=UNIDADE_CHOICES
    )
    formulacao = models.CharField(
        "Formulação", max_length=40, choices=FORMULACAO_CHOICES
    )
    tipo = models.CharField("Tipo", max_length=40, choices=TIPO_CHOICES)
    
    id_farmbox = models.IntegerField("ID FarmBox", blank=True, null=True)

    class Meta:
        ordering = ["produto"]
        verbose_name = "Defensivo"
        verbose_name_plural = "Defensivos"

    def __str__(self):
        return self.produto


class Cultura(Base):
    cultura = models.CharField(
        "Cultura", max_length=100, help_text="Cultura", unique=True
    )
    id_d = models.PositiveIntegerField("ID_D", unique=True)
    id_farmbox = models.IntegerField("ID FarmBox", unique=True, blank=True, null=True)
    id_protheus_planejamento = models.CharField(
        "ID Cultura", max_length=20, null=True, blank=True, help_text=" ID Cultura Planejamento Agrícola Protheus"
    )
    tipo_producao = models.CharField(
        "Tipo Produção", max_length=20, null=True, blank=True
    )

    map_color = models.CharField(
        "Cor no Mapa", max_length=150, null=True, blank=True, unique=True
    )
    map_color_line = models.CharField(
        "Cor do Contorno no Mapa", max_length=150, null=True, blank=True, unique=True
    )

    class Meta:
        ordering = ["cultura"]
        verbose_name = "Cultura"
        verbose_name_plural = "Culturas"
        indexes = [models.Index(fields=["cultura"])]

    def __str__(self):
        return self.cultura


class Variedade(Base):
    variedade = models.CharField("Variedade", max_length=100, unique=True)
    id_farmbox = models.IntegerField("ID FarmBox", unique=True, blank=True, null=True)
    nome_fantasia = models.CharField(
        "Nome Fant.", max_length=100, blank=True, null=True
    )
    id_protheus_planejamento_second_option = models.CharField(
        "ID Cultura/Variedade", max_length=20, null=True, blank=True, help_text=" ID Cultura/Variedade Planejamento Agrícola Protheus"
    )
    
    id_cultura_dif_protheus_planejamento = models.CharField(
        "ID Cultura", max_length=20, null=True, blank=True, help_text=" ID Cultura Planejamento Agrícola Protheus / mesma cultura diferentes codigos ( feijao)"
    )
    
    cultura = models.ForeignKey(Cultura, on_delete=models.PROTECT)
    dias_ciclo = models.PositiveIntegerField("Quantidade Dias do Ciclo", default=0)
    dias_germinacao = models.PositiveIntegerField(
        "Quantidade Dias da Germinação", default=5
    )

    map_oppacity = models.CharField(
        "Opacidade no Mapa", max_length=150, null=True, blank=True
    )

    class Meta:
        ordering = ["variedade"]
        verbose_name = "Variedade"
        verbose_name_plural = "Variedades"
        indexes = [models.Index(fields=["variedade"])]

    def __str__(self):
        return self.variedade


#  ------------- ------------- PRODUCAO -------------  -------------#
class Safra(Base):
    safra = models.CharField("Safra", max_length=100, help_text="Safra", unique=True)
    id_farmbox = models.IntegerField("ID FarmBox", unique=True, blank=True, null=True)
    class Meta:
        # ordering = ["safra"]
        verbose_name = "Safra"
        verbose_name_plural = "Safras"
        indexes = [models.Index(fields=["safra"])]

    def __str__(self):
        return self.safra


class Ciclo(Base):
    ciclo = models.PositiveBigIntegerField("ciclo", help_text="Ciclo", unique=True)

    class Meta:
        # ordering = ["ciclo"]
        verbose_name = "Ciclo"
        verbose_name_plural = "Ciclos"
        indexes = [models.Index(fields=["ciclo"])]

    def __str__(self):
        return str(self.ciclo)


class Programa(Base):
    nome = models.CharField(
        "Nome Programa",
        max_length=120,
        help_text="Nome do Programa",
        blank=True,
        null=True,
    )
    nome_fantasia = models.CharField(
        "Nome Fantasia Programa",
        max_length=40,
        help_text="Nome Fantasia do Programa",
        blank=True,
        null=True,
    )
    safra = models.ForeignKey(Safra, on_delete=models.PROTECT, blank=True, null=True)
    ciclo = models.ForeignKey(Ciclo, on_delete=models.PROTECT, blank=True, null=True)
    cultura = models.ForeignKey(
        Cultura, on_delete=models.PROTECT, blank=True, null=True
    )
    variedade = models.ManyToManyField(Variedade, blank=True, default=None, related_name="variedade_programa")
    programa_por_data = models.BooleanField(
        "Regra por data",
        default=True,
        help_text="Define se o programa é calculado por data",
    )
    programa_por_estagio = models.BooleanField(
        "Regra por estágio",
        default=False,
        help_text="Define se o programa é calculado por Estágio",
    )

    start_date = models.DateField(
        help_text="dd/mm/aaaa - Data Prevista Inínicio Programa / Plantio",
        blank=True,
        null=True,
    )

    end_date = models.DateField(
        help_text="dd/mm/aaaa - Data Prevista Término Programa / Plantio",
        blank=True,
        null=True,
    )

    versao = models.IntegerField("Versão Atual", blank=True, null=True, default=1)

    class Meta:
        # ordering = ["variedade"]
        verbose_name = "Programa"
        verbose_name_plural = "Programas"
        indexes = [models.Index(fields=["nome"])]

    def __str__(self):
        return f"{self.nome}"


class Operacao(Base):
    estagio = models.CharField(
        "Estagio", max_length=120, help_text="Nome do Estágio", blank=True, null=True
    )
    operacao_numero = models.IntegerField("Número da Operação", blank=True, null=True)
    programa = models.ForeignKey(
        Programa,
        on_delete=models.PROTECT,
        related_name="programa_related_operacao",
        blank=True,
        null=True,
    )
    prazo_dap = models.IntegerField("DAP - Dias Após Plantio", blank=True, null=True)
    prazo_emergencia = models.IntegerField("Dias da Emergencia", blank=True, null=True)

    base_dap = models.BooleanField(
        "Prazo Base da Operação por DAP",
        default=False,
        help_text="Informar se a Operação é pelo prazo do Plantio",
    )

    base_emergencia = models.BooleanField(
        "Prazo Base da Operação por Emergencia",
        default=False,
        help_text="Informar se a Operação é pelo prazo de Emergencia",
    )

    estagio_iniciado = models.BooleanField(
        "Estagio Iniciado",
        default=False,
        help_text="Informar quando o estágio iniciar",
    )
    estagio_finalizado = models.BooleanField(
        "Estagio Finalizado",
        default=False,
        help_text="Informar quando o estágio finalizar",
    )

    base_operacao_anterior = models.BooleanField(
        "Base ültima Operação",
        default=False,
        help_text="Infomrar se esta operação tem como base a data de aplicação da Operação anterior",
    )

    dias_base_operacao_anterior = models.IntegerField(
        "Dias de Janela Após a aplicação anterior", blank=True, null=True
    )

    obs = models.TextField("Observação", max_length=500, blank=True)

    map_color = models.CharField("Cor no Mapa", max_length=150, null=True, blank=True)

    @property
    def operation_to_dict(self):
        query = Aplicacao.objects.select_related("operacao").filter(
            ativo=True, operacao=self.id
        )
        produtos = [
            {
                "dose": str(dose_produto.dose),
                "tipo": dose_produto.defensivo.tipo,
                "produto": dose_produto.defensivo.produto,
                "id_farmbox": dose_produto.defensivo.id_farmbox,
                "formulacao": dose_produto.defensivo.unidade_medida,
                "quantidade aplicar": "",
            }
            for dose_produto in query
        ]

        return produtos

    @property
    def operation_done_to_add(self):
        query = Aplicacao.objects.select_related("operacao").filter(
            ativo=True, operacao=self.id
        )
        produtos = [
            {
                "dose": str(dose_produto.dose),
                "tipo": dose_produto.defensivo.tipo,
                "produto": dose_produto.defensivo.produto,
                "id_farmbox": dose_produto.defensivo.id_farmbox,
                "formulacao": dose_produto.defensivo.unidade_medida,
                "quantidade aplicar": "",
            }
            for dose_produto in query
        ]
        operation = {
            "dap": self.prazo_dap,
            "estagio": self.estagio,
            "aplicado": False,
            "enviado_farmbox": False,
            "produtos": produtos,
            "data prevista": "",
        }
        return operation

    class Meta:
        unique_together = ("estagio", "programa")
        ordering = ["programa", "operacao_numero"]
        verbose_name = "Programa - Operação"
        verbose_name_plural = "Programas - Operações"

    def __str__(self):
        return self.estagio


class MoedaChoices(models.TextChoices):
    BRL = 'BRL', 'R$'
    USD = 'USD', 'USD'

class Aplicacao(Base):
    operacao = models.ForeignKey(
        Operacao, on_delete=models.PROTECT, related_name="programa_related_aplicacao"
    )
    defensivo = models.ForeignKey(Defensivo, on_delete=models.PROTECT)
    dose = models.DecimalField(
        "Dose KG/LT por ha",
        help_text="Dose aplicada de Kg ou Lt por ha.",
        max_digits=10,
        decimal_places=4,
    )
    obs = models.TextField("Observação", max_length=500, blank=True)
    
    preco = models.DecimalField("Preço unitário", max_digits=10, decimal_places=4, default=0, blank=True, null=True)
    moeda = models.CharField("Moeda", max_length=3, choices=MoedaChoices.choices, default=MoedaChoices.BRL, blank=True, null=True)
    valor_final = models.DecimalField("Valor final (R$)", max_digits=12, decimal_places=4, editable=False, default=0, blank=True, null=True)
    valor_aplicacao = models.DecimalField("Valor total aplicado (R$)", max_digits=14, decimal_places=4, editable=False, default=0, blank=True, null=True)

    class Meta:
        unique_together = ("operacao", "defensivo", "ativo", "dose")
        ordering = ["operacao", "defensivo"]
        verbose_name = "Programa - Operações/Aplicações"
        verbose_name_plural = "Programas - Operações/Aplicações"

    def __str__(self):
        return f"{self.defensivo} - {self.dose} - {self.ativo} - {self.operacao.programa.nome_fantasia}"
    
    def calcular_valores(self):
        if self.preco is None or self.dose is None:
            self.valor_final = None
            self.valor_aplicacao = None
            return

        if self.moeda == MoedaChoices.USD:
            try:
                cotacao = CotacaoDolar.objects.latest("data").valor
            except CotacaoDolar.DoesNotExist:
                cotacao = Decimal("0")
            self.valor_final = (self.preco * cotacao).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        else:
            self.valor_final = self.preco

        self.valor_aplicacao = (self.valor_final * self.dose).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def save(self, *args, **kwargs):
        if self.preco is not None and self.dose is not None:
            self.calcular_valores()
        super().save(*args, **kwargs)


#  ------------- ------------- xxxxxxxxxx -------------  -------------#


class Plantio(Base):
    safra = models.ForeignKey(Safra, on_delete=models.PROTECT)
    ciclo = models.ForeignKey(Ciclo, on_delete=models.PROTECT)
    talhao = models.ForeignKey(
        Talhao, related_name="plantios", on_delete=models.PROTECT
    )
    programa = models.ForeignKey(
        Programa,
        on_delete=models.PROTECT,
        related_name="programa_related_plantio",
        blank=True,
        null=True,
        limit_choices_to={"ativo": True},
    )
    variedade = models.ForeignKey(
        Variedade,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
    )
    finalizado_plantio = models.BooleanField(
        "Finalizado Plantio", default=False, help_text="Finalizado o Plantio"
    )
    
    inicializado_plantio = models.BooleanField(
        "Plantio Começou", default=False, help_text="Informar se começou o plantio"
    )
    finalizado_colheita = models.BooleanField(
        "Finalizado Colheita", default=False, help_text="Finalizada a Colheita"
    )

    area_aproveito = models.BooleanField(
        "Area Aprov.", default=False, help_text="Apontar caso seja Area de Aproveito"
    )
    
    area_planejamento_plantio = models.DecimalField(
        "Area Planejada para o Plantio", help_text="Area Planejada / ha", max_digits=8, decimal_places=2, default=0, blank=True, null=True
    )
    
    area_colheita = models.DecimalField(
        "Area Colheita", help_text="Area Plantada / ha", max_digits=8, decimal_places=2
    )
    area_parcial = models.DecimalField(
        "Area P. Colhida",
        help_text="Area Parcial / ha",
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
    )

    data_plantio = models.DateField(
        help_text="dd/mm/aaaa - Data Efetiva de Plantio",
        blank=True,
        null=True,
    )

    data_prevista_plantio = models.DateField(
        help_text="dd/mm/aaaa - Data Projetada para o Plantio",
        blank=True,
        null=True,
    )

    data_prevista_colheita = models.DateField(
        help_text="dd/mm/aaaa - Data Projetada para a Colheita",
        blank=True,
        null=True,
    )

    data_emergencia = models.DateField(
        help_text="dd/mm/aaaa - Data Emergencia Talhao ", blank=True, null=True
    )

    veiculos_carregados = models.IntegerField("Veículos Carregados / Talhao", default=0)

    area_aferida = models.BooleanField(
        "Área Aferida",
        default=False,
        help_text="Informa se houve a medição da área após o plantio",
    )

    plantio_descontinuado = models.BooleanField(
        "Plantio Descontinuado", default=False, help_text="Plantio interrompido ?"
    )

    replantio = models.BooleanField(
        "Replantio",
        default=False,
        help_text="Apontar caso tenha ocorrido replantio nesta Parcela / Safra / Ciclo",
    )
    
    farmbox_update = models.BooleanField(
        "Atualziar via Farmbox",
        default=True,
        help_text="Falso caso não seja pra atualizar com os dados do Farmbox",
    )

    talhao_desativado = models.BooleanField(
        "Parcela Desativada",
        default=False,
        help_text="Apontar caso a Parcela tenha sido desativada nesta Safra / Ciclo",
    )

    cronograma_programa = models.JSONField(null=True, blank=True)
    map_centro_id = models.JSONField(null=True, blank=True)
    map_geo_points = models.JSONField(null=True, blank=True)
    id_farmbox = models.PositiveIntegerField(
        "ID Plantio Farmbox",
        help_text="Id de cada plantio do farmbox",
        blank=True,
        null=True,
        unique=True,
    )
    
    acompanhamento_medias = models.BooleanField(
        "Acompanhamento das Médias", default=True, help_text="Acompanha as médias do Plantio / Safra?"
    )

    @property
    def get_dap(self):
        dap = 0
        today = datetime.date.today()
        if self.data_plantio:
            dap = today - self.data_plantio
            dap = dap.days + 1
        return dap

    get_dap.fget.short_description = "DAP"

    @property
    def get_cronograma_programa(self):
        cronograma = [
            {
                "Data Plantio": self.data_plantio,
                "Area_plantio": self.area_colheita,
                "id": self.id,
            }
        ]
        qs = Operacao.objects.select_related("programa").all()
        qs = [x for x in qs if x.programa == self.programa]
        # queryset = Aplicacao.objects.select_related("operacao").filter(
        #     operacao__programa=self.programa
        # )
        if len(qs) > 0:
            for i in qs:
                data_plantio = (
                    self.data_plantio if self.data_plantio else self.programa.start_date
                )
                produtos = []
                if data_plantio:
                    prazo = i.prazo_dap if i.prazo_dap is not None else 0
                    etapa = {
                        "Estagio": i.estagio,
                        "dap": i.prazo_dap,
                        "Data Prevista": data_plantio + datetime.timedelta(days=prazo),
                        "produtos": produtos,
                    }
                    cronograma.append(etapa)
                else:
                    print(f"Sem Data de Plantio {data_plantio}")
        return cronograma

    get_cronograma_programa.fget.short_description = "Programação Programa"

    @property
    def get_detail_cronograma_and_aplication(self):
        cronograma = [
            {
                "Data Plantio": self.data_plantio,
                "Area_plantio": self.area_colheita,
                "id": self.id,
            }
        ]
        qs = Operacao.objects.select_related("programa").filter(ativo=True)
        qs = [x for x in qs if x.programa == self.programa]
        queryset = Aplicacao.objects.select_related("operacao").filter(
            operacao__programa=self.programa
        )
        if len(qs) > 0:
            for i in qs:
                data_plantio = (
                    self.data_plantio if self.data_plantio else self.programa.start_date
                )
                produtos = []
                for dose_produto in queryset:
                    if (
                        i.estagio == dose_produto.operacao.estagio
                        and dose_produto.ativo == True
                    ):
                        produtos.append(
                            {
                                "produto": dose_produto.defensivo.produto,
                                "dose": dose_produto.dose,
                                "quantidade_total": dose_produto.dose
                                * self.area_colheita,
                            }
                        )
                if data_plantio:
                    etapa = {
                        "Estagio": i.estagio,
                        "dap": i.prazo_dap,
                        "Data Prevista": data_plantio
                        + datetime.timedelta(days=i.prazo_dap),
                        "produtos": produtos,
                    }
                    cronograma.append(etapa)
                else:
                    print(f"Sem Data de Plantio {data_plantio}")
        return cronograma

    @property
    def create_json_cronograma_aplications(self):
        cronograma = [
            {
                "Data Plantio": format_date_json(self.data_plantio),
                "Area_plantio": str(self.area_colheita),
                "id": self.id,
            }
        ]
        qs = Operacao.objects.select_related("programa").filter(ativo=True)
        qs = [x for x in qs if x.programa == self.programa]
        queryset = Aplicacao.objects.select_related("operacao").filter(
            operacao__programa=self.programa
        )
        if len(qs) > 0:
            for i in qs:
                data_plantio = (
                    self.data_plantio if self.data_plantio else self.programa.start_date
                )
                produtos = []
                for dose_produto in queryset:
                    if (
                        i.estagio == dose_produto.operacao.estagio
                        and dose_produto.ativo == True
                    ):
                        produtos.append(
                            {
                                "produto": dose_produto.defensivo.produto,
                                "tipo": dose_produto.defensivo.tipo,
                                "id_farmbox": dose_produto.defensivo.id_farmbox,
                                "formulacao": dose_produto.defensivo.unidade_medida,
                                "dose": str(dose_produto.dose),
                                "quantidade aplicar": str(
                                    round(
                                        (
                                            decimal.Decimal(dose_produto.dose)
                                            * decimal.Decimal(self.area_colheita)
                                        ),
                                        3,
                                    )
                                ),
                            }
                        )
                if data_plantio:
                    time_delta_prazo = (
                        i.prazo_dap if i.prazo_dap <= 0 else i.prazo_dap - 1
                    )
                    etapa = {
                        "estagio": i.estagio,
                        "aplicado": True if i.prazo_dap <= 0 else False,
                        "dap": i.prazo_dap,
                        "enviado_farmbox": False,
                        "data prevista": format_date_json(
                            str(data_plantio), datetime.timedelta(days=time_delta_prazo)
                        ),
                        "produtos": produtos,
                    }
                    cronograma.append(etapa)
                else:
                    print(f"Sem Data de Plantio {data_plantio}")

        return cronograma

    get_detail_cronograma_and_aplication.fget.short_description = (
        "Detalhes de Aplicações"
    )

    @property
    def get_data_prevista_colheita_base_dap(self):
        prazo = self.variedade.dias_ciclo
        return self.data_plantio + datetime.timedelta(days=prazo)

    def save(self, *args, **kwargs):
        if (
            self.pk is not None
            and self.cronograma_programa is None
            and self.data_plantio is not None
        ):
            if self.programa:
                newVal = self.create_json_cronograma_aplications
                self.cronograma_programa = newVal
        if (
            self.pk is not None
            and self.data_plantio is None
            and self.cronograma_programa is not None
        ):
            self.cronograma_programa = None
        super(Plantio, self).save(*args, **kwargs)

    class Meta:
        unique_together = ("safra", "ciclo", "talhao")
        ordering = ["data_plantio"]
        verbose_name = "Plantio"
        verbose_name_plural = "Plantios"
        indexes = [
            models.Index(
                fields=[
                    "safra",
                    "ciclo",
                    "talhao",
                    "programa",
                    "variedade",
                    "data_plantio",
                ]
            )
        ]

    def __str__(self):
        if self.variedade is not None:
            return f"{self.talhao.id_talhao} | {self.talhao.fazenda.nome} | {self.safra}-{self.ciclo} | {self.variedade.variedade}| {str(self.area_colheita)}"
        return f"{self.talhao.id_talhao} | {self.talhao.fazenda.nome} | {self.safra}-{self.ciclo} | {str(self.area_colheita)}"

class PlantioExtratoArea(Base):
    plantio = models.ForeignKey(Plantio,on_delete=models.PROTECT)

    area_plantada = models.DecimalField(
        "Area plantada",
        help_text="Area Parcial Plantada",
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
    )

    data_plantio = models.DateField(
        help_text="dd/mm/aaaa - Data Efetiva de Plantio",
        null=True
    )

    aguardando_chuva = models.BooleanField(
        "Plantio Aguardando a chuva",
        default=False,
        help_text="Apontar caso o Plantio esteja aguardando a chuva",
    )
    
    finalizado_plantio = models.BooleanField(
        "Plantio da parcela finalizado",
        default=False,
        help_text="Informar se o plantio da parcela encerrou",
    )

    def save(self, *args, **kwargs):
        
        if self.ativo == True:
            print('Extrato ativo')
            plantio = self.plantio
            area_informada = self.area_plantada if self.area_plantada else 0
            if self.pk:
                total_area = PlantioExtratoArea.objects.filter(plantio=plantio, ativo=True).exclude(pk=self.pk).aggregate(
                    total_area_plantada=Sum("area_plantada")
                )['total_area_plantada'] or 0
            else:
                # For new instances, include all areas
                total_area = PlantioExtratoArea.objects.filter(plantio=plantio, ativo=True).aggregate(
                    total_area_plantada=Sum("area_plantada")
                )['total_area_plantada'] or 0
            
            # print("Plantio to update: ", plantio)
            # print('salvando area plantada para o plantio', total_area)
            # print('area informada: ', self.area_plantada)
            if self.finalizado_plantio:
                plantio.area_colheita = plantio.area_planejamento_plantio
                plantio.finalizado_plantio = True
                if self.area_plantada:
                    pass
                else:
                    self.area_plantada = plantio.area_planejamento_plantio - total_area
                
            else:
                plantio.area_colheita = total_area + area_informada
            plantio.inicializado_plantio = True
            
            # if data plantio is NONE, ADD DATA PLANTIO AND GENERATE PROGRAM
            if plantio.data_plantio is None:
                print('plantio sem data até o momento ', plantio.data_plantio)
                print('Nova data plantio: ', self.data_plantio)
                plantio.data_plantio = self.data_plantio
            plantio.save()
        super(PlantioExtratoArea, self).save(*args, **kwargs)

    def __str__(self):
        return f'{self.plantio.talhao.fazenda.nome} | {self.plantio.talhao.id_talhao} | {self.plantio.safra}-{self.plantio.ciclo} | {str(self.area_plantada)}'

    class Meta:
        ordering = ["data_plantio", 'plantio']
        verbose_name = 'Extrato do Plantio'
        verbose_name_plural = 'Extrato dos Plantios'


class ColheitaPlantioExtratoArea(Base):
    plantio = models.ForeignKey(Plantio,on_delete=models.PROTECT)
    area_colhida = models.DecimalField(
        "Area Colhida",
        help_text="Area Parcial Colhida",
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
    )
    
    data_colheita = models.DateField(
        help_text="dd/mm/aaaa - Data Efetiva de Colheita",
        blank=True,
        null=True,
    )
    
    time = models.TimeField(blank=True, null=True)
    
    class Meta:
        unique_together = ('time', 'data_colheita', 'plantio')
        ordering = ["data_colheita", 'plantio']
        verbose_name = 'Extrato da Colheita'
        verbose_name_plural = 'Extrato das Colheitas'


class Colheita(Base):
    AlphanumericValidator = RegexValidator(
        r"^[0-9a-zA-Z]*$", "Somente letras e números permitido."
    )

    plantio = models.ForeignKey(
        Plantio, on_delete=models.PROTECT, related_name="plantio_colheita", db_index=True
    )
    data_colheita = models.DateField(help_text="dd/mm/aaaa", blank=True, null=True)
    romaneio = models.CharField(
        "Romaneio", max_length=40, help_text="Número do Romaneio"
    )
    placa = models.CharField(
        "Placa",
        max_length=7,
        help_text="Placa do Veículo",
        validators=[AlphanumericValidator, MinLengthValidator(7)],
    )
    motorista = models.CharField(
        "Nome Motorista", max_length=40, help_text="Nome do Motorista"
    )

    ticket = models.CharField("Ticket", max_length=20, blank=True, null=True)
    op = models.CharField("OP", max_length=20, blank=True, null=True, unique=True)

    peso_tara = models.PositiveIntegerField(
        "Peso Tara",
        help_text="Informe o Peso Tara do Veículo",
    )

    peso_bruto = models.PositiveIntegerField(
        "Peso Bruto",
        help_text="Informe o Peso Bruto do Veículo",
    )

    umidade = models.DecimalField(
        "Umidade",
        help_text="Informe a Umidade da Carga",
        max_digits=4,
        decimal_places=2,
        blank=True,
        null=True,
    )

    desconto_umidade = models.DecimalField(
        "Desc. Umidade",
        help_text="Desconto Umidade Calculado",
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
    )

    impureza = models.DecimalField(
        "Impureza",
        help_text="Informe a impureza da Carga",
        max_digits=4,
        decimal_places=2,
        blank=True,
        null=True,
    )

    desconto_impureza = models.DecimalField(
        "Desc. Impureza",
        help_text="Desconto Impureza Calculado",
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
    )

    bandinha = models.DecimalField(
        "Bandinha",
        help_text="Informe a Bandinha da Carga",
        max_digits=4,
        decimal_places=2,
        blank=True,
        null=True,
    )

    desconto_bandinha = models.DecimalField(
        "Desc. Bandinha",
        help_text="Desconto Bandinha Calculado",
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
    )

    peso_liquido = models.DecimalField(
        "Peso Liquido",
        help_text="Peso Líquido Calculado",
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
    )

    peso_scs_liquido = models.DecimalField(
        "Sacos Liquido",
        help_text="Peso Líquido Calculado em Sacos de 60Kg",
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
    )

    peso_scs_limpo_e_seco = models.DecimalField(
        "Sacos Limpo e Seco",
        help_text="Peso Limpo e Seco Calculado em Sacos de 60Kg",
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
    )

    deposito = models.ForeignKey(
        Deposito, on_delete=models.PROTECT, related_name="deposito_colheita", db_index=True
    )
    
    id_farmtruck = models.CharField(
        "ID Plantio Farmtruck APP",
        max_length=100,
        blank=True,
        null=True,
    )

    # @property
    # def peso_saco_umido(self):
    #     return self.peso_umido / 60

    # @property
    # def peso_saco_liquido(self):
    #     return self.peso_liquido / 60

    def save(self, *args, **kwargs):
        umidade_dict = {
            "Arroz": 12,
            "Soja": 14,
            "Feijão": 14,
        }
        impureza_dict = {
            "Arroz": 2,
            "Soja": 0,
            "Feijão": 0,
        }
        if self.umidade is not None:
            peso_liquido = decimal.Decimal(self.peso_bruto - self.peso_tara)
            if self.umidade > umidade_dict[self.plantio.variedade.cultura.cultura]:
                unit_d = decimal.Decimal(
                    umidade_dict[self.plantio.variedade.cultura.cultura] / 1000
                )
                desconto_umidade = (
                    (
                        (
                            self.umidade
                            - umidade_dict[self.plantio.variedade.cultura.cultura]
                        )
                        * 100
                        * unit_d
                    )
                    * peso_liquido
                    / 100
                )
                self.desconto_umidade = desconto_umidade
                print("desconto umidade ", desconto_umidade)
            else:
                self.desconto_umidade = 0

        if self.impureza is not None:
            # REGRA FAZENDAO
            descontar_imp_num = 0
            if self.impureza > impureza_dict[self.plantio.variedade.cultura.cultura]:
                descontar_imp_num = (
                    self.impureza
                    - impureza_dict[self.plantio.variedade.cultura.cultura]
                )
            if self.deposito.id_d == 4:
                good_imp = 1
                if self.impureza >= good_imp:
                    descontar_imp_num = self.impureza - good_imp
                else:
                    descontar_imp_num = 0
            peso_liquido = decimal.Decimal(self.peso_bruto - self.peso_tara)
            desconto_impureza = (peso_liquido * descontar_imp_num) / 100
            self.desconto_impureza = desconto_impureza
            print("Impureza ", desconto_impureza)

        print(self.bandinha)
        if self.bandinha is not None:
            peso_liquido = decimal.Decimal(self.peso_bruto - self.peso_tara)
            desconto_bandinha = (peso_liquido * self.bandinha) / 100
            self.desconto_bandinha = desconto_bandinha
            print("Bandinha", desconto_bandinha)
        if self.bandinha == None:
            self.bandinha = 0
            self.desconto_bandinha = 0

        self.peso_liquido = decimal.Decimal(self.peso_bruto - self.peso_tara)
        self.peso_scs_limpo_e_seco = self.peso_liquido
        if self.desconto_umidade:
            self.peso_liquido = self.peso_liquido - self.desconto_umidade
            self.peso_scs_limpo_e_seco = (
                self.peso_scs_limpo_e_seco - self.desconto_umidade
            )
        if self.desconto_impureza:
            self.peso_liquido = self.peso_liquido - self.desconto_impureza
            self.peso_scs_limpo_e_seco = (
                self.peso_scs_limpo_e_seco - self.desconto_impureza
            )
        if self.desconto_bandinha:
            self.peso_liquido = self.peso_liquido - self.desconto_bandinha

        self.peso_scs_liquido = self.peso_liquido / 60
        self.peso_scs_limpo_e_seco = self.peso_scs_limpo_e_seco / 60
        super(Colheita, self).save(*args, **kwargs)

    class Meta:
        unique_together = (("plantio", "romaneio", "ticket"))
        ordering = ["data_colheita"]
        verbose_name = "Colheita"
        verbose_name_plural = "Colheitas"
        indexes = [
            models.Index(fields=["plantio", "data_colheita"]),
        ]

    def __str__(self):
        return f"{self.romaneio} | {self.plantio.talhao.id_talhao} - {self.plantio.talhao.fazenda.nome} | {str(round(self.peso_liquido,2))}"


class PlantioDetail(Plantio):
    class Meta:
        proxy = True
        verbose_name = "Plantio - Resumo Colheita"
        verbose_name_plural = "Plantios - Resumo Colheita"


class PlantioDetailPlantio(Plantio):
    class Meta:
        proxy = True
        verbose_name = "Plantio - Resumo Plantio"
        verbose_name_plural = "Plantios - Resumo Plantio"


class AplicacaoPlantio(Base):
    plantio = models.ForeignKey(
        Plantio,
        on_delete=models.PROTECT,
    )
    estagio = models.ForeignKey(
        Operacao,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
    )
    defensivo = models.ForeignKey(Defensivo, on_delete=models.PROTECT)
    dose = models.DecimalField(
        "Dose KG/LT por ha",
        help_text="Dose aplicada de Kg ou Lt por ha.",
        max_digits=8,
        decimal_places=3,
    )
    data_prevista = models.DateField(
        help_text="dd/mm/aaaa - Data Prevista Aplicação",
        blank=True,
        null=True,
    )
    aplicado = models.BooleanField(
        "Aplicação Efetuada",
        default=False,
        help_text="Informar se a Aplicação foi realizada",
    )

    obs = models.TextField("Observação", max_length=500, blank=True)

    class Meta:
        unique_together = ("plantio", "estagio", "defensivo")
        # ordering = ["data_colheita"]
        verbose_name = "Aplicação Plantio"
        verbose_name_plural = "Aplicações Plantio"

    def __str__(self):
        return f"{self.estagio} - {self.defensivo} - {self.dose}"


class CicloAtual(Base):
    nome = models.CharField(
        "Safra / Ciclo Atual", max_length=150, null=True, blank=True
    )
    safra = models.ForeignKey(Safra, on_delete=models.PROTECT)
    ciclo = models.ForeignKey(Ciclo, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "Safra - Ciclo Atual"
        verbose_name_plural = "Safra - Ciclo Atuais"

    def __str__(self):
        return f"{self.safra} - {self.ciclo}"


class PlannerPlantio(Base):
    projeto = models.ForeignKey(Projeto, on_delete=models.PROTECT)
    cultura = models.ForeignKey(Cultura, on_delete=models.PROTECT)
    variedade = models.ForeignKey(
        Variedade, on_delete=models.PROTECT, blank=True, null=True
    )
    safra = models.ForeignKey(Safra, on_delete=models.PROTECT)
    ciclo = models.ForeignKey(Ciclo, on_delete=models.PROTECT)
    start_date = models.DateField(
        help_text="Data Prevista Início Programa / Plantio",
        blank=True,
        null=True,
    )
    area = models.DecimalField(
        "Area Prevista",
        help_text="Informar Area Prevista",
        blank=True,
        null=True,
        max_digits=10,
        decimal_places=2,
    )

    class Meta:
        verbose_name = "Planejamento Plantio"
        verbose_name_plural = "Planejamento Plantios"
        unique_together = ("projeto", "cultura", "ciclo", "safra", "start_date")
        ordering = ["start_date"]

    def __str__(self):
        return f"{self.projeto} - {self.safra}-{self.ciclo} - {self.start_date} - {self.cultura}"


class Visitas(Base):
    fazenda = models.ForeignKey(Fazenda, on_delete=models.PROTECT)
    projeto = models.ManyToManyField(Projeto)
    data = models.DateField(
        "Data Visita", help_text="dd/mm/aaaa - Data efetiva da Visita"
    )
    resp_visita = models.CharField(
        "Responsável pela Visita",
        help_text="Pessoa que foi visitar a fazenda",
        max_length=100,
        blank=True,
        null=True,
    )
    resp_fazenda = models.CharField(
        "Responsável Recebedor da Fazenda",
        help_text="Pessoa que foi receber a visita na fazenda",
        max_length=100,
        blank=True,
        null=True,
    )
    observacoes_gerais = models.TextField("Observações Gerais", blank=True, null=True)

    class Meta:
        ordering = ["-data"]
        verbose_name = "Visita"
        verbose_name_plural = "Visitas"
        # unique_together = ("fazenda", "data", "projeto")

    def __str__(self):
        return f"{self.data} - {self.fazenda.nome}"


def get_img_upload_path(instance, filename):
    base_path = "visitas"
    file_name = f"{instance.visita.data}_{instance.visita.fazenda.nome}/"
    return os.path.join(base_path, file_name, filename)

def get_nf_path(instance, filename):
    base_path = "notasfiscais"
    file_name = f"{instance.defensivo.produto}/"
    return os.path.join(base_path, file_name, filename)


class RegistroVisitas(Base):
    visita = models.ForeignKey(Visitas, on_delete=models.PROTECT)
    image = models.ImageField("Imagem", upload_to=get_img_upload_path)
    image_link_url = models.URLField(
        "Link da Imagem", blank=True, null=True, max_length=250
    )
    image_title = models.CharField(
        "Título da Imagem", blank=True, null=True, max_length=100
    )
    obs = models.TextField("Obs", blank=True, null=True)

    @property
    def image_url(self):
        if self.image:
            return self.image.url
        return ""  # or some default

    class Meta:
        ordering = ["criados"]
        verbose_name = "Visita - Registro"
        verbose_name_plural = "Visitas - Registros"

    def __str__(self):
        if self.image_title:
            return self.image_title
        return "Imagem sem Titulo"

    # def save(self, *args, **kwargs):
    #     super().save(*args, **kwargs)
    #     # Dropbox API
    #     dropbox_access_token = settings.DROPBOX_OAUTH2_REFRESH_TOKEN
    #     dbx = dropbox.Dropbox(dropbox_access_token)

    #     file_name = os.path.basename(self.image.path)

    #     # Upload the file to Dropbox
    #     # with open(self.image.path, "rb") as f:
    #     #     response = dbx.files_upload(f.read(), "/" + file_name)
    #     # Generate shared link
    #     # shared_link_metadata = dbx.sharing_create_shared_link(response.path_display)
    #     file_link_metadata = dbx.sharing_create_shared_link_with_settings(
    #         self.image.name
    #     )
    #     downloadable_url = file_link_metadata.url.replace("dl=0", "dl=1")
    #     # Save the shared link to the model
    #     print(downloadable_url)

    #     self.image_link_url = downloadable_url
    #     super().save(*args, **kwargs)


class AppFarmboxIntegration(Base):
    app_nuumero = models.CharField('AP Número', max_length=200, null=True, blank=True)
    app_fazenda = models.CharField('Fazenda AP', max_length=200, null=True, blank=True)
    app         = models.JSONField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'Aps Integração'
        verbose_name_plural = 'Aps Integrações'

class StProtheusIntegration(Base):
    st_numero = models.CharField('ST Número', max_length=200, null=True, blank=True)
    st_fazenda = models.CharField('Fazenda ST', max_length=200, null=True, blank=True)
    app         = models.JSONField('Detalhes', null=True, blank=True)
    
    class Meta:
        verbose_name = 'ST Integração'
        verbose_name_plural = 'STs Integrações'

class HeaderPlanejamentoAgricola(Base):
    projeto = models.ForeignKey(Projeto, on_delete=models.PROTECT)
    codigo_planejamento = models.CharField('Código do Planejamento', max_length=200)
    safra = models.ForeignKey(Safra, on_delete=models.PROTECT)
    ciclo = models.ForeignKey(Ciclo, on_delete=models.PROTECT)
    
    class Meta:
        unique_together = ("projeto", "safra", "ciclo")
        verbose_name = 'Header Planejamento Agrícola'
        verbose_name_plural =  'Headers Planejamentos Agrícola'
    
    def __str__(self):
        return f'{self.projeto} {self.safra} {self.ciclo} {self.codigo_planejamento}'


class BuyProducts(Base):
    defensivo           = models.ForeignKey(Defensivo, on_delete=models.PROTECT)
    quantidade_comprada = models.DecimalField('Quantidade Comprada em Kg', max_digits=12 , decimal_places=2)
    fazenda             = models.ForeignKey(Fazenda, on_delete=models.PROTECT)
    projeto             = models.ManyToManyField(Projeto)
    sit_pago            = models.BooleanField("Satus Pagamento" , default=False)
    data_pagamento      = models.DateField('Data Pagamento', blank=True, null=True)
    nota_fiscal         = models.CharField("Número da Nota Fiscal", max_length=255, blank=True, null=True)
    nf_file             = models.FileField("NF", upload_to=get_nf_path, blank=True, null=True)
    fornecedor          = models.CharField("Fornecedor", max_length=255, blank=True, null=True)
    nr_pedido           = models.CharField("Número do pedido", max_length=255, blank=True, null=True)
    
    
    class Meta:
        verbose_name = "Produto Comprado"
        verbose_name_plural = "Produtos Comprados"
        ordering = ["defensivo"]
    
    def __str__(self) -> str:
        return f'{self.defensivo.produto} - {self.fazenda.nome}'

class SentSeeds(Base):
    data_envio      = models.DateField(help_text="dd/mm/aaaa - Data Envio da Semente", blank=True, null=True)
    variedade       = models.ForeignKey(Variedade, on_delete=models.PROTECT, blank=True, null=True, default=9)
    quantidade_bags = models.IntegerField("Quantidade de Bags Enviados", blank=True, null=True)
    peso_bag        = models.DecimalField('Peso dos Bags Enviados em Kg', max_digits=12 , decimal_places=2,default=700)
    peso_total      = models.DecimalField('Peso total da carga enviada em Kg', max_digits=12 , decimal_places=2, blank=True, null=True)
    nota_fiscal     = models.CharField("Número da Nota Fiscal", max_length=255, blank=True, null=True, unique=True)
    origem          = models.ForeignKey(Fazenda, on_delete=models.PROTECT, blank=True, null=True,  related_name="related_origem_semente", default=17)
    destino         = models.ForeignKey(Fazenda, on_delete=models.PROTECT, blank=True, null=True, related_name="related_destino_semente")
    safra           = models.ForeignKey(Safra, on_delete=models.PROTECT, blank=True, null=True, default=3)
    ciclo           = models.ForeignKey(Ciclo, on_delete=models.PROTECT, blank=True, null=True, default=5)
    
    
    
    def save(self, *args, **kwargs):
        if self.quantidade_bags is not None and self.peso_bag is not None:
            self.peso_total = self.peso_bag * self.quantidade_bags
        super(SentSeeds, self).save(*args, **kwargs)
    
    
    class Meta:
        verbose_name = "Envio de Semente"
        verbose_name_plural = "Envio de Sementes"
        ordering = ["-data_envio"]
    
    def __str__(self) -> str:
        return f'{self.data_envio} - {self.destino.nome} - {self.peso_total}'

class SeedStock(Base):
    data_apontamento = models.DateField(help_text="dd/mm/aaaa - Data Apontamento do Estoque", blank=True, null=True)
    estoque_atual    = models.DecimalField('Estoque Atual na Data em Kg', max_digits=12 , decimal_places=2)
    variedade        = models.ForeignKey(Variedade, on_delete=models.PROTECT, blank=True, null=True)
    fazenda          = models.ForeignKey(Fazenda, on_delete=models.PROTECT, blank=True, null=True,  related_name="related_origem_semente_estoque")
    
    
    class Meta:
        verbose_name = "Estoque de Semente"
        verbose_name_plural = "Estoque de Sementes"
        ordering = ["-data_apontamento"]
    
    def __str__(self) -> str:
        return f'{self.data_apontamento} - {self.fazenda.nome} - {self.estoque_atual}'
class SeedConfig(Base):
    data_apontamento = models.DateField(help_text="dd/mm/aaaa - Data última Regulagem", blank=True, null=True)
    regulagem        = models.DecimalField('Regulagem das Plantadeiras em Kg/ha', max_digits=12 , decimal_places=2)
    fazenda          = models.ForeignKey(Fazenda, on_delete=models.PROTECT, blank=True, null=True,  related_name="related_origem_semente_regulagem")
    variedade        = models.ForeignKey(Variedade, on_delete=models.PROTECT, blank=True, null=True)
    
    
    class Meta:
        verbose_name = "Regulagem da Plantadeira"
        verbose_name_plural = "Regulagem das Plantadeiras"
        ordering = ["-data_apontamento"]
    
    def __str__(self) -> str:
        return f'{self.data_apontamento} - {self.fazenda.nome} - {self.regulagem}'


class BackgroundTaskStatus(Base): 
    task_id    = models.CharField(max_length=100, unique=True)
    task_name  = models.CharField(max_length=100)
    status     = models.CharField(max_length=50, default='pending')  # pending, running, done, failed
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at   = models.DateTimeField(null=True, blank=True)
    result     = models.JSONField(null=True, blank=True)
    
    
    class Meta:
        verbose_name = "Background Task"
        verbose_name_plural = 'Background Tasks'
        ordering = ["-criados"]
        
    def __str__(self) -> str:
        return f'{self.task_id} - {self.task_name} - {self.status}'