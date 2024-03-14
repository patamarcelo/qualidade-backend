from django.db import models
from diamante.models import Projeto, Cultura, TIPO_CHOICES, Defensivo, Safra, Ciclo

import os
from django.db.models import F

# Create your models here.


class Base(models.Model):
    criados = models.DateTimeField("Criação", auto_now_add=True)
    modificado = models.DateTimeField("Atualização", auto_now=True)
    ativo = models.BooleanField("Ativo", default=True)
    observacao = models.TextField("Observação", blank=True, null=True)

    class Meta:
        abstract = True


# -------------  ------------- ESTRUTURA -------------  -------------#


class TecnicoAgricola(Base):
    nome = models.CharField("Nome", max_length=100, unique=True)
    crea_number = models.CharField("Numero do CREA", max_length=100, unique=True)

    class Meta:
        verbose_name = "Técnico Agrícola"
        verbose_name_plural = "Técnicos Agrícola"

    def __str__(self) -> str:
        return f"{self.nome} - {self.crea_number}"


class Aeronave(Base):
    prefixo = models.CharField("Prefixo Aero", max_length=100, unique=True)

    class Meta:
        verbose_name = "Aeronave"
        verbose_name_plural = "Aeronaves"

    def __str__(self) -> str:
        return self.prefixo


class Pista(Base):
    projeto = models.ForeignKey(Projeto, on_delete=models.PROTECT)
    nome = models.CharField("Nome da Pista", blank=True, null=True, max_length=100)
    coordenadas = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = "Pista"
        verbose_name_plural = "Pistas"

    def __str__(self) -> str:
        return f"{self.projeto.nome} - {self.nome}"


class Piloto(Base):
    nome = models.CharField("Nome", blank=True, null=True, max_length=100)
    anac = models.CharField("Nº ANAC", max_length=100, null=True, blank=True)

    class Meta:
        verbose_name = "Piloto"
        verbose_name_plural = "Pilotos"

    def __str__(self) -> str:
        return self.nome


class EngenheiroAgronomo(Base):
    nome = models.CharField("Nome", max_length=100, unique=True)
    crea_number = models.CharField("Numero do CREA", max_length=100, unique=True)

    class Meta:
        verbose_name = "Técnico Agrícola"
        verbose_name_plural = "Técnicos Agrícola"

    def __str__(self) -> str:
        return f"{self.nome} - {self.crea_number}"


class Ajudante(Base):
    nome = models.CharField("Nome Ajudante", max_length=100, null=True, blank=True)

    class Meta:
        verbose_name = "Ajudante"
        verbose_name_plural = "Ajudantes"

    def __str__(self) -> str:
        return self.nome


class Gerente(Base):
    nome = models.CharField("Nome do Gerente", max_length=100, null=True, blank=True)
    projeto = models.ManyToManyField(Projeto)

    class Meta:
        verbose_name = "Gerente"
        verbose_name_plural = "Gerentes"

    def __str__(self) -> str:
        return self.nome


def get_img_upload_path(instance, filename):
    base_path = "aviacao"
    file_name = f"{instance.numero}_{instance.criados}/"
    return os.path.join(base_path, file_name, filename)


class TabelaPilotos(Base):
    safra = models.ForeignKey(Safra, on_delete=models.PROTECT)
    ciclo = models.ForeignKey(Ciclo, on_delete=models.PROTECT)
    vazao = models.PositiveIntegerField()
    preco = models.DecimalField("Preço por Hectare",
        blank=True,
        null=True,
        max_digits=10,
        decimal_places=2,)
    
    class Meta: 
        verbose_name = "Preço do Piloto"
        verbose_name_plural = "Preços dos Pilotos"
    
    def __str__(self):
        return f'{self.safra.safra}-{self.ciclo.ciclo} / R$ {self.preco} -{self.vazao}kg/hs '

class OrdemDeServico(Base):
    numero = models.PositiveIntegerField(unique=True)
    data = models.DateField("Data", help_text="dd/mm/aaaa")
    ajudante = models.ManyToManyField(Ajudante)
    area = models.DecimalField(
        "Area",
        help_text="Informar Área da Aplicação",
        blank=True,
        null=True,
        max_digits=10,
        decimal_places=2,
    )
    encarregado_autoriza = models.ForeignKey(Gerente, on_delete=models.PROTECT)
    combustivel = models.DecimalField(
        "Combustível / Litros",
        help_text="Informar Quantidade de Combustível",
        blank=True,
        null=True,
        max_digits=10,
        decimal_places=2,
    )
    valor_combustivel = models.DecimalField(
        "Valor do Combustível por Litro",
        blank=True,
        null=True,
        max_digits=10,
        decimal_places=2,
    )
    cultura = models.ForeignKey(Cultura, on_delete=models.PROTECT)
    os_file = models.ImageField("Ordem de Serviço", upload_to=get_img_upload_path)
    data_inicial = models.DateField("Data Inicial Aplicação", help_text="dd/mm/aaaa")
    data_final = models.DateField("Data Final Aplicação", help_text="dd/mm/aaaa")
    horimetro_inicial = models.DecimalField(
        "Horímetro Inicial",
        blank=True,
        null=True,
        max_digits=10,
        decimal_places=2,
    )

    horimetro_final = models.DecimalField(
        "Horímetro Final",
        blank=True,
        null=True,
        max_digits=10,
        decimal_places=2,
    )

    tempo_aplicacao = models.GeneratedField(
        expression=F("horimetro_final") - F("horimetro_inicial"),
        output_field=models.DecimalField(
            "Tempo Aplicacao",
            blank=True,
            null=True,
            max_digits=10,
            decimal_places=2,
        ),
        db_persist=True,
    )

    oleo_lubrificante = models.DecimalField(
        "Óelo Lubrificante",
        help_text="Quantidade de óleo Utilizado",
        blank=True,
        null=True,
        max_digits=10,
        decimal_places=2,
    )

    tipo_servico = models.CharField("Tipo Serviço", max_length=80, choices=TIPO_CHOICES)
    uso_gps = models.BooleanField(
        "Utilizado o GPS ? ",
        default=False,
        help_text="Informar se foi utilizado o GPS do Avião",
    )
    volume = models.DecimalField(
        "Volume Litros ou Kg/ha",
        help_text="Informar Volume Utilizado por hectare",
        blank=True,
        null=True,
        max_digits=10,
        decimal_places=2,
    )
    projeto = models.ForeignKey(Projeto, on_delete=models.PROTECT)
    aeronave = models.ForeignKey(Aeronave, on_delete=models.PROTECT)
    engenheiro_agronomo = models.ForeignKey(EngenheiroAgronomo, on_delete=models.PROTECT, blank=True, null=True)
    piloto = models.ForeignKey(Piloto, on_delete=models.PROTECT)
    pista = models.ForeignKey(Pista, on_delete=models.PROTECT)
    tecnico_agricola_executor = models.ForeignKey(TecnicoAgricola, on_delete=models.PROTECT, blank=True, null=True)
    
    
    class Meta:
        verbose_name = "Ordem de Serviço"
        verbose_name_plural = "Ordens de Serviço"
        
    
    def __str__(self):
        return f'OS Nº {self.numero}'
    
    
class CondicoesMeteorologicas(Base):
    os = models.ForeignKey(OrdemDeServico, on_delete=models.PROTECT)
    temperatura_inicial = models.PositiveIntegerField()
    temperatura_final = models.PositiveIntegerField()
    umidade_relativa_incial = models.PositiveIntegerField()
    umidade_relativa_final = models.PositiveIntegerField()
    velocidade_vento_inicial = models.PositiveIntegerField()
    velocidade_vento_final = models.PositiveIntegerField()
    
    class Meta:
        verbose_name = "Condições Metereológicas"
        verbose_name_plural = "Condições Metereológicas"
        
    
    def __str__(self):
        return self.os.numero

class TempoAplicacao(Base):
    os = models.ForeignKey(OrdemDeServico, on_delete=models.PROTECT)
    inicio_aplicacao = models.DateTimeField('Início da Aplicação')
    final_aplicacao = models.DateTimeField('Final da Aplicação')
    
    class Meta: 
        verbose_name = "Tempo Aplicação"
        verbose_name_plural = "Tempo Aplicação"
        
    def __str__(self):
        return self.os.numero

class ParametrosAplicacao(Base):
    pass

class AplicacaoAviao(Base):
    os = models.ForeignKey(OrdemDeServico, on_delete=models.PROTECT, related_name="os_related_aplicacao")
    defensivo = models.ForeignKey(Defensivo, on_delete=models.PROTECT)
    dose = models.DecimalField(
        "Dose KG/LT por ha",
        help_text="Dose aplicada de Kg ou Lt por ha.",
        max_digits=8,
        decimal_places=3,
    )
    obs = models.TextField("Observação", max_length=500, blank=True)

    class Meta:
        unique_together = ("os", "defensivo", "ativo", "dose")
        ordering = ["os", "defensivo"]
        verbose_name = "Aplicação Avião"
        verbose_name_plural = "Aplicações Avião"

    def __str__(self):
        return f"{self.defensivo} - {self.dose} - {self.ativo} - {self.os.numero}"
