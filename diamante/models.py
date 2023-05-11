from django.db import models
from django.utils import timezone

from datetime import timedelta
import datetime

from django.db import connection

connection.queries

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
    ("fertilizante", "Fertilizante"),
    ("fungicida", "Fungicida"),
    ("herbicida", "Herbicida"),
    ("inseticida", "Inseticida"),
    ("lubrificante", "Lubrificante"),
    ("nutricao", "Nutrição"),
    ("oleo_mineral_vegetal", "Óleo Mineral/Vegetal"),
    ("regulador", "Regulador"),
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

    class Meta:
        ordering = ["cultura"]
        verbose_name = "Cultura"
        verbose_name_plural = "Culturas"

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

    class Meta:
        ordering = ["variedade"]
        verbose_name = "Variedade"
        verbose_name_plural = "Variedades"

    def __str__(self):
        return self.variedade


#  ------------- ------------- PRODUCAO -------------  -------------#
class Safra(Base):
    safra = models.CharField("Safra", max_length=100, help_text="Safra", unique=True)

    class Meta:
        ordering = ["safra"]
        verbose_name = "Safra"
        verbose_name_plural = "Safras"

    def __str__(self):
        return self.safra


class Ciclo(Base):
    ciclo = models.PositiveBigIntegerField("ciclo", help_text="Ciclo", unique=True)

    class Meta:
        ordering = ["ciclo"]
        verbose_name = "Ciclo"
        verbose_name_plural = "Ciclos"

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

    class Meta:
        # ordering = ["variedade"]
        verbose_name = "Programa"
        verbose_name_plural = "Programas"

    def __str__(self):
        return self.nome_fantasia


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

    class Meta:
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
        return f"{self.defensivo} - {self.dose}"


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

    @property
    def get_dap(self):
        dap = 0
        today = datetime.date.today()
        if self.data_plantio:
            dap = today - self.data_plantio
            dap = dap.days
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
        qs = Operacao.objects.select_related("programa").all()
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
                    produtos.append(
                        {
                            "produto": dose_produto.defensivo.produto,
                            "dose": dose_produto.dose,
                            "quantidade_total": dose_produto.dose * self.area_colheita,
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

    get_detail_cronograma_and_aplication.fget.short_description = (
        "Detalhes de Aplicações"
    )

    @property
    def get_data_prevista_colheita_base_dap(self):
        prazo = self.variedade.dias_ciclo
        return self.data_plantio + datetime.timedelta(days=prazo)

    class Meta:
        unique_together = ("safra", "ciclo", "talhao")
        ordering = ["data_plantio"]
        verbose_name = "Plantio"
        verbose_name_plural = "Plantios"

    def __str__(self):
        return f"{self.talhao.id_talhao} | {self.talhao.fazenda.nome} | {str(self.area_colheita)}"


class Colheita(Base):
    plantio = models.ForeignKey(Plantio, on_delete=models.PROTECT)
    data_colheita = models.DateField(help_text="dd/mm/aaaa", blank=True, null=True)
    romaneio = models.CharField(
        "Romaneio", max_length=40, help_text="Número do Romaneio"
    )
    placa = models.CharField("Placa", max_length=40, help_text="Placa do Veículo")
    motorista = models.CharField(
        "Nome Motorista", max_length=40, help_text="Nome do Motorista"
    )

    peso_umido = models.DecimalField(
        "Peso Úmido",
        help_text="Peso Líquido Antes dos descontos",
        max_digits=14,
        decimal_places=2,
    )
    peso_liquido = models.DecimalField(
        "Peso Líquido",
        help_text="Peso Líquido Depois dos descontos",
        max_digits=14,
        decimal_places=2,
    )
    deposito = models.ForeignKey(Deposito, on_delete=models.PROTECT)

    # @property
    # def peso_saco_umido(self):
    #     return self.peso_umido / 60

    # @property
    # def peso_saco_liquido(self):
    #     return self.peso_liquido / 60

    class Meta:
        unique_together = (
            "plantio",
            "romaneio",
        )
        ordering = ["data_colheita"]
        verbose_name = "Colheita"
        verbose_name_plural = "Colheitas"

    def __str__(self):
        return f"{self.romaneio} | {self.plantio.talhao.id_talhao} | {self.plantio.talhao.fazenda.nome} | {str(self.peso_liquido)}"
