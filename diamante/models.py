from django.db import models

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
        ordering = ["id_talhao"]
        verbose_name = "Talhao"
        verbose_name_plural = "Talhoes"

    def __str__(self):
        return f"{self.id_talhao}"


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


#  ------------- ------------- xxxxxxxxxx -------------  -------------#
