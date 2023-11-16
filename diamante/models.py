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

from django.db.models import Count

# Create your models here.


class Base(models.Model):
    criados = models.DateTimeField("Criação", auto_now_add=True)
    modificado = models.DateTimeField("Atualização", auto_now=True)
    ativo = models.BooleanField("Ativo", default=True)

    class Meta:
        abstract = True


# -------------  ------------- ESTRUTURA -------------  -------------#


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

    capacidade_plantio_ha_dia = models.PositiveIntegerField(
        "Quantidade ha Plantio / dia",
        default=50,
        help_text="Capacidade Projetada Plantio ha/dia",
    )

    class Meta:
        ordering = ["nome"]
        verbose_name = "Fazenda"
        verbose_name_plural = "Fazenda"

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
        verbose_name_plural = "Projeto"

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

UNIDADE_CHOICES = (("l_ha", "LT"), ("kg_ha", "KG"))
FORMULACAO_CHOICES = (("liquido", "Líquido"), ("solido", "Sólido"))

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
                "quantidade aplicar": "",
            }
            for dose_produto in query
        ]
        operation = {
            "dap": self.prazo_dap,
            "estagio": self.estagio,
            "aplicado": False,
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


class Aplicacao(Base):
    operacao = models.ForeignKey(
        Operacao, on_delete=models.PROTECT, related_name="programa_related_aplicacao"
    )
    defensivo = models.ForeignKey(Defensivo, on_delete=models.PROTECT)
    dose = models.DecimalField(
        "Dose KG/LT por ha",
        help_text="Dose aplicada de Kg ou Lt por ha.",
        max_digits=8,
        decimal_places=3,
    )
    obs = models.TextField("Observação", max_length=500, blank=True)

    class Meta:
        ordering = ["operacao", "defensivo"]
        verbose_name = "Programa - Operações/Aplicações"
        verbose_name_plural = "Programas - Operações/Aplicações"

    def __str__(self):
        return f"{self.defensivo} - {self.dose} - {self.ativo} - {self.operacao.programa.nome_fantasia}"


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
    finalizado_colheita = models.BooleanField(
        "Finalizado Colheita", default=False, help_text="Finalizada a Colheita"
    )
    area_aproveito = models.BooleanField(
        "Area Aprov.", default=False, help_text="Apontar caso seja Area de Aproveito"
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

    plantio_descontinuado = models.BooleanField(
        "Plantio Descontinuado", default=False, help_text="Plantio interrompido ?"
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
        return f"{self.talhao.id_talhao} | {self.talhao.fazenda.nome} | {self.safra}-{self.ciclo} | {self.variedade.variedade}| {str(self.area_colheita)}"


class Colheita(Base):
    AlphanumericValidator = RegexValidator(
        r"^[0-9a-zA-Z]*$", "Somente letras e números permitido."
    )

    plantio = models.ForeignKey(
        Plantio, on_delete=models.PROTECT, related_name="plantio_colheita"
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

    ticket = models.CharField(
        "Ticket", max_length=20, blank=True, null=True, unique=True
    )
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

    deposito = models.ForeignKey(Deposito, on_delete=models.PROTECT)

    # @property
    # def peso_saco_umido(self):
    #     return self.peso_umido / 60

    # @property
    # def peso_saco_liquido(self):
    #     return self.peso_liquido / 60

    def save(self, *args, **kwargs):
        if self.umidade is not None:
            peso_liquido = decimal.Decimal(self.peso_bruto - self.peso_tara)
            if self.umidade > 14:
                unit_d = decimal.Decimal(14 / 1000)
                desconto_umidade = (
                    ((self.umidade - 14) * 100 * unit_d) * peso_liquido / 100
                )
                self.desconto_umidade = desconto_umidade
                print("desconto umidade ", desconto_umidade)
            else:
                self.desconto_umidade = 0

        if self.impureza is not None:
            peso_liquido = decimal.Decimal(self.peso_bruto - self.peso_tara)
            desconto_impureza = (peso_liquido * self.impureza) / 100
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
        unique_together = (("plantio", "romaneio", "ticket"), ("romaneio", "plantio"))
        ordering = ["data_colheita"]
        verbose_name = "Colheita"
        verbose_name_plural = "Colheitas"

    def __str__(self):
        return f"{self.romaneio} | {self.plantio.talhao.id_talhao} | {self.plantio.talhao.fazenda.nome} | {str(round(self.peso_liquido,2))}"


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
