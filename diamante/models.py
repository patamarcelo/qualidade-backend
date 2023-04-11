from django.db import models
from django.utils import timezone

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

    class Meta:
        ordering = ["nome"]
        verbose_name = "Fazenda"
        verbose_name_plural = "Fazenda"

    def __str__(self):
        return self.nome


class Projeto(Base):
    nome = models.CharField("Nome", max_length=100, help_text="Projeto", unique=True)
    id_d = models.IntegerField("ID_D", unique=True)
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
        order_with_respect_to = 'fazenda'
        verbose_name = "Talhao"
        verbose_name_plural = "Talhoes"

    def __str__(self):
        return f"{self.fazenda.nome} - {self.id_talhao}"


# -------------  ------------- PRODUTO -------------  -------------#


class Cultura(Base):
    cultura = models.CharField(
        "Cultura", max_length=100, help_text="Cultura", unique=True
    )
    id_d = models.PositiveIntegerField("ID_D", unique=True)
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
        pass

    class Operacao(Base):
        pass
    
    class Aplicacoes(Base):
        pass

#  ------------- ------------- xxxxxxxxxx -------------  -------------#


class Plantio(Base):
    safra              = models.ForeignKey(Safra, on_delete=models.PROTECT)
    ciclo              = models.ForeignKey(Ciclo, on_delete=models.PROTECT)
    talhao             = models.ForeignKey(Talhao, related_name="plantios", on_delete=models.PROTECT)
    variedade          = models.ForeignKey(Variedade, on_delete=models.PROTECT)
    finalizado_plantio = models.BooleanField(
        "Finalizado", default=True, help_text="Finalizado o Plantio"
    )
    finalizado_colheita = models.BooleanField(
        "Finalizado", default=False, help_text="Finalizada a Colheita"
    )
    area_aproveito = models.BooleanField(
        "Area Aproveito", default=False, help_text="Apontar caso seja Area de Aproveito"
    )
    area_colheita = models.DecimalField(
        "Area Colheita", help_text="Area Plantada / ha", max_digits=8, decimal_places=2
    )
    area_parcial = models.DecimalField(
        "Area Parcial Colhida",
        help_text="Area Parcial / ha",
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
    )
    data_plantio = models.DateField(
        default=timezone.now, help_text="dd/mm/aaaa", blank=True, null=True
    )
    
    veiculos_carregados = models.IntegerField("Veículos Carregados / Talhao", default=0)

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
    romaneio = models.CharField(
        "Romaneio", max_length=40, help_text="Número do Romaneio", unique=True
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
